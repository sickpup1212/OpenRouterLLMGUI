"""LLM Query Window for interacting with language models."""

import tkinter as tk
from tkinter import ttk, Text, Toplevel, messagebox, filedialog
import threading
import json
import os
import base64
import logging
import requests
import re
import html

from gui.markdown_renderer import MarkdownRenderer
from gui.diff_viewer import DiffViewerWindow
from gui.other_windows import SelectProfileWindow, UseFileWindow
from llm.client import LLMClient
from llm.agent import AgentManager
from llm.schemas import OpenRouterAPIParameters
from llm.token_counter import TokenCounter, estimate_tokens
from tools.batch_executor import create_batch_function

logger = logging.getLogger(__name__)


class LLMQueryWindow(Toplevel):
    """A separate window for querying a specific LLM configuration."""
    def __init__(self, app, config_name, config_details, initial_prompt=None, initial_response=None):
        super().__init__(app.root)
        self.title(f"Query: {config_name}")
        self.geometry("900x700")
        self.config_name = config_name
        self.config_details = config_details
        self.app = app
        self.advanced_settings = {}
        self.current_profile_name = "Default"
        self.uploaded_image_data = None
        self.generated_image = None
        self.history = []  # For conversation history
        self.token_counter = TokenCounter()

        # Create a dedicated LLMClient and AgentManager for this window
        try:
            api_key = self.config_details.get("api_key")
            model_name = self.config_details.get("model")

            if not api_key or not model_name:
                raise ValueError("Config is missing API key or model")

            # 1. Create this window's LLMClient
            self.llm_client = LLMClient(api_key, model_name)

            # 2. Create this window's own tool registry, starting with the app's base
            self.window_tool_registry = self.app.tool_registry.copy()

            # 3. Create this window's AgentManager
            self.agent_manager = AgentManager(
                self.app.agent_directory,
                self.llm_client,
                self.window_tool_registry,
                self.app.agent_tool_schemas,
                max_iterations=20
            )

            # 4. Add the agent manager's tools to this window's registry
            self.window_tool_registry["call_agent"] = self.agent_manager.call_agent
            self.window_tool_registry["get_agent_names"] = self.agent_manager.get_agent_names

            # 5. Set the agent manager's final tool mapping
            self.agent_manager.tool_mapping = self.window_tool_registry
            batch_func = create_batch_function(self.agent_manager.tool_mapping)
            self.window_tool_registry["BATCH"] = batch_func
            self.agent_manager.tool_mapping["BATCH"] = batch_func

        except Exception as e:
            logger.error(f"Failed to init agent manager for query window: {e}")
            messagebox.showerror("Agent Init Error", f"Failed to initialize agent manager for this window: {e}\n\nAgent tools (call_agent) will not work.")
            # Fallback to just the app's tools
            self.llm_client = None
            self.agent_manager = None
            self.window_tool_registry = self.app.tool_registry.copy()

        self.create_widgets(initial_prompt, initial_response)
        self.create_context_menus()
        self.update_title()

    # --- NEW HELPER FUNCTION ---
    def _format_todo_html(self, todo_json_string: str) -> str:
        """Parses a todo JSON response and returns a formatted HTML block."""
        try:
            data = json.loads(todo_json_string)
            todos = data.get('todos', [])
            
            html_parts = ["<div style='font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 12px; background-color: #fcfcfc;'>"]
            html_parts.append("<h4 style='margin-top: 0; margin-bottom: 10px; color: #333;'>Todo List Update</h4>")
            
            if not todos:
                html_parts.append("<p><em>Todo list is empty.</em></p>")
            else:
                html_parts.append("<ul style='list-style-type: none; padding-left: 0; margin-bottom: 10px;'>")
                for task in todos:
                    status = task.get('status', 'pending')
                    content = task.get('content', 'No content')
                    # Escape HTML in content
                    content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

                    checked = 'checked' if status == 'completed' else ''
                    style = 'text-decoration: line-through; color: #888;' if checked else 'color: #111;'
                    
                    html_parts.append(f"""
                        <li style='margin-bottom: 5px; {style}'>
                            <input type='checkbox' disabled {checked} style='margin-right: 8px;'>
                            {content}
                        </li>
                    """)
                html_parts.append("</ul>")

            # Add summary
            summary = f"""
                <p style='font-size: 0.9em; color: #555; margin-bottom: 0;'>
                    <strong>Total:</strong> {data.get('total', 0)} | 
                    <strong>Pending:</strong> {data.get('pending', 0)} | 
                    <strong>Completed:</strong> {data.get('completed', 0)}
                </p>
            """
            html_parts.append(summary)
            html_parts.append("</div>")
            
            return "".join(html_parts)

        except json.JSONDecodeError:
            return f"<p>Error parsing todo JSON.</p>"
        except Exception as e:
            return f"<p>Error formatting todo HTML: {e}</p>"
    # --- END NEW HELPER FUNCTION ---
    def _escape_html(self, text: str) -> str:
        """A basic HTML escaper."""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _process_html_for_code_blocks(self, html_content: str, code_block_counter: int) -> (str, int):
        """Finds code blocks, adds copy buttons, and stores their content."""
        pattern = re.compile(r'(<pre><code.*?>.*?</code></pre>)', re.DOTALL)

        last_end = 0
        processed_html = []
        for match in pattern.finditer(html_content):
            processed_html.append(html_content[last_end:match.start()])

            block_html = match.group(1)
            block_id = f"block-{code_block_counter}"
            code_block_counter += 1

            raw_code = re.sub('<[^<]+?>', '', block_html)
            self.code_blocks[block_id] = html.unescape(raw_code)

            container = (
                f'<div class="code-block-container">'
                f'<a href="copy-code://{block_id}" class="copy-code-btn">Copy</a>'
                f'{block_html}'
                f'</div>'
            )
            processed_html.append(container)
            last_end = match.end()

        processed_html.append(html_content[last_end:])
        return "".join(processed_html), code_block_counter

    def _copy_code_to_clipboard(self, block_id: str):
        """Copy the code from a specific block to the clipboard."""
        code_content = self.code_blocks.get(block_id)
        if code_content:
            try:
                # Use the tkinter clipboard functionality
                self.clipboard_clear()
                self.clipboard_append(code_content)
                self.update()  # Required on some platforms
                logger.info(f"Copied code block {block_id} to clipboard.")
                # We can't give direct feedback on the button, this is a limitation
            except tk.TclError:
                logger.error("Failed to copy to clipboard. Tkinter clipboard not available.")
            except Exception as e:
                logger.error(f"An unexpected error occurred during copy: {e}")

    def _handle_link_click(self, url: str):
        """Callback to handle clicks on special links in the HtmlFrame."""
        if url.startswith("copy-code://"):
            block_id = url.split("copy-code://")[1]
            self._copy_code_to_clipboard(block_id)
        # Add handling for other custom schemes or standard http links if needed
        elif url.startswith("http"):
            try:
                import webbrowser
                webbrowser.open_new(url)
            except Exception as e:
                logger.error(f"Failed to open URL '{url}': {e}")


    def safe_enable_send_button(self):
        """Safely enable send button, checking if window still exists."""
        try:
            if self.winfo_exists():
                self.send_button.config(state=tk.NORMAL)
        except:
            pass  # Window was destroyed, ignore

    def show_diff_popup(self, original_content, updated_content, filename):
        """
        Display a diff viewer popup and return user's decision.

        Args:
            original_content (str): Original file content
            updated_content (str): Proposed new content
            filename (str): Name of the file being modified

        Returns:
            bool: True if user accepts, False if user rejects
        """
        diff_window = DiffViewerWindow(self, original_content, updated_content, filename)
        return diff_window.result if diff_window.result is not None else False

    def _count_tokens_from_response(self, api_response: dict, messages: list):
        """
        Extract and count tokens from API response.

        Args:
            api_response: The JSON response from the API
            messages: The messages sent in the request
        """
        try:
            # Increment API call counter
            self.token_counter.increment_call()

            # Try to get usage data from API response (OpenRouter provides this)
            usage = api_response.get('usage', {})

            if usage:
                # Use exact counts from API if available
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)

                self.token_counter.add_input(prompt_tokens)
                self.token_counter.add_output(completion_tokens)

                logger.info(f"Token count - Input: {prompt_tokens}, Output: {completion_tokens}")
            else:
                # Fallback: estimate tokens if API doesn't provide usage data
                logger.warning("API response missing 'usage' data, using estimation")

                # Estimate input tokens from messages
                input_text = ""
                for msg in messages:
                    content = msg.get('content', '')
                    if isinstance(content, str):
                        input_text += content
                    elif isinstance(content, list):
                        for item in content:
                            if item.get('type') == 'text':
                                input_text += item.get('text', '')

                input_tokens = estimate_tokens(input_text)
                self.token_counter.add_input(input_tokens)

                # Estimate output tokens from response
                response_content = api_response.get('choices', [{}])[0].get('message', {}).get('content', '')
                output_tokens = estimate_tokens(response_content)
                self.token_counter.add_output(output_tokens)

                logger.info(f"Estimated tokens - Input: {input_tokens}, Output: {output_tokens}")

        except Exception as e:
            logger.error(f"Error counting tokens: {e}", exc_info=True)

    def scroll_to_bottom(self):
        """Scroll the HtmlFrame to the bottom."""
        try:
            # Move to the bottom (1.0 = 100% down)
            self.chat_display.yview_moveto(1.0)
        except Exception as e:
            print(f"Scroll error: {e}")

    def create_widgets(self, initial_prompt, initial_response):
        # Main container
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid weights for proper resizing
        main_frame.rowconfigure(1, weight=1)  # Chat area gets all extra space
        main_frame.rowconfigure(0, weight=0)  # Top bar fixed
        main_frame.rowconfigure(2, weight=0)  # Input area fixed
        main_frame.columnconfigure(0, weight=1)

        # Top button bar
        top_bar = ttk.Frame(main_frame)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(top_bar, text="New Conversation", command=self.start_new_conversation).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_bar, text="Load Profile", command=self.open_select_profile_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="Upload Image", command=self.upload_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="Use File", command=self.use_file).pack(side=tk.LEFT, padx=5)

        # Add diff mode checkbox
        self.diff_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_bar, text="Diff Mode", variable=self.diff_mode_var).pack(side=tk.LEFT, padx=5)

        # Add count_tokens checkbox
        self.count_tokens_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_bar, text="Count Tokens", variable=self.count_tokens_var).pack(side=tk.LEFT, padx=5)

        save_menu_button = ttk.Menubutton(top_bar, text="Save")
        save_menu = tk.Menu(save_menu_button, tearoff=0)
        save_menu.add_command(label="Save Last Prompt", command=self.save_prompt)
        save_menu.add_command(label="Save Last Response", command=self.save_response)
        save_menu.add_command(label="Save Full History", command=self.save_both)
        save_menu_button['menu'] = save_menu
        save_menu_button.pack(side=tk.LEFT, padx=5)

        # Chat display area with HtmlFrame
        chat_frame = ttk.Frame(main_frame)
        chat_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        chat_frame.rowconfigure(0, weight=1)
        chat_frame.columnconfigure(0, weight=1)

        # Use HtmlFrame for rendered HTML
        try:
            from tkinterweb import HtmlFrame
            # Create a dictionary to hold the content of code blocks for copying
            self.code_blocks = {}
            self.chat_display = HtmlFrame(
                chat_frame,
                messages_enabled=False,
                link_clicked_callback=self._handle_link_click
            )
            self.chat_display.grid(row=0, column=0, sticky="nsew")
            self.using_html = True
        except ImportError:
            # Fallback to regular Text widget if tkinterweb not available
            self.chat_display = Text(chat_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Arial", 11))
            self.chat_display.grid(row=0, column=0, sticky="nsew")
            chat_scrollbar = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self.chat_display.yview)
            chat_scrollbar.grid(row=0, column=1, sticky="ns")
            self.chat_display['yscrollcommand'] = chat_scrollbar.set
            self.markdown_renderer = MarkdownRenderer(self.chat_display)
            self.using_html = False

        # Input area
        input_frame = ttk.Frame(main_frame)
        input_frame.grid(row=2, column=0, sticky="ew")
        input_frame.columnconfigure(0, weight=1)

        self.prompt_entry = Text(input_frame, height=3, font=("Arial", 10))
        self.prompt_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.prompt_entry.bind("<Return>", self.send_on_enter)
        self.prompt_entry.bind("<Shift-Return>", self.insert_newline)

        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_query_threaded)
        self.send_button.grid(row=0, column=1)

        self.prompt_entry.focus_set()

        if initial_prompt:
            self.prompt_entry.insert("1.0", initial_prompt)
        if initial_response:
            self.history.append({"role": "assistant", "content": initial_response})
            self.update_chat_display()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def send_on_enter(self, event=None):
        self.send_query_threaded()
        return "break"

    def insert_newline(self, event=None):
        self.prompt_entry.insert(tk.INSERT, "\n")
        return "break"

    def start_new_conversation(self):
        """Start a new conversation - clears history."""
        self.history = []
        self.clear_uploaded_image()
        self.prompt_entry.delete("1.0", tk.END)
        self.token_counter.reset()
        if self.using_html:
            self.update_chat_display()
        else:
            self.append_to_chat_display("--- New conversation started ---\n", "system")

    def save_prompt(self):
        """Save the last user prompt from history."""
        last_user_prompt = None
        for item in reversed(self.history):
            if item['role'] == 'user':
                content = item['content']
                if isinstance(content, list):
                    text_parts = [part['text'] for part in content if part.get('type') == 'text']
                    last_user_prompt = '\n'.join(text_parts)
                else:
                    last_user_prompt = content
                break

        if not last_user_prompt:
            messagebox.showwarning("Save Error", "No prompt found in history.", parent=self)
            return

        self.app.add_saved_item("Prompt", self.config_details['model'], last_user_prompt, "")
        messagebox.showinfo("Success", "Last prompt saved.", parent=self)

    def save_response(self):
        """Save the last assistant response from history."""
        last_assistant_response = None
        for item in reversed(self.history):
            if item['role'] == 'assistant':
                last_assistant_response = item.get('content')
                break
        if not last_assistant_response:
            messagebox.showwarning("Save Error", "No response found in history.", parent=self)
            return
        self.app.add_saved_item("Response", self.config_details['model'], "", last_assistant_response)
        messagebox.showinfo("Success", "Last response saved.", parent=self)

    def save_both(self):
        """Save the entire conversation history."""
        if not self.history:
            messagebox.showwarning("Save Error", "History is empty.", parent=self)
            return
        conversation_text = []
        for item in self.history:
            role = item.get('role')
            content = item.get('content')
            if role == 'user':
                conversation_text.append("You:")
                if isinstance(content, list):
                    for part in content:
                        if part.get('type') == 'text':
                            conversation_text.append(part['text'])
                        elif part.get('type') == 'image_url':
                            conversation_text.append("[Image]")
                else:
                    conversation_text.append(content)
                conversation_text.append("")
            elif role == 'assistant':
                if content:
                    conversation_text.append("Assistant:")
                    conversation_text.append(content)
                    conversation_text.append("")
        full_history_text = '\n'.join(conversation_text)
        if not full_history_text.strip():
            messagebox.showwarning("Save Error", "No content to save.", parent=self)
            return
        self.app.add_saved_item("History", self.config_details['model'], full_history_text, "")
        messagebox.showinfo("Success", "Full conversation history saved.", parent=self)

    def upload_image(self):
        """Upload an image to be sent with the next message."""
        file_path = filedialog.askopenfilename(
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.webp *.gif *.bmp"),
                ("All Files", "*.*")
            ]
        )
        if not file_path:
            return
        try:
            file_ext = file_path.split('.')[-1].lower()
            valid_extensions = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp']
            if file_ext not in valid_extensions:
                messagebox.showwarning("Invalid File",
                    "Please select a valid image file (PNG, JPG, JPEG, WEBP, GIF, BMP)",
                    parent=self)
                return
            with open(file_path, "rb") as image_file:
                image_data = image_file.read()
                encoded_string = base64.b64encode(image_data).decode('utf-8')
            mime_type = f"image/{file_ext}"
            if file_ext == 'jpg':
                mime_type = "image/jpeg"
            self.uploaded_image_data = f"data:{mime_type};base64,{encoded_string}"

            messagebox.showinfo("Image Ready",
                f"Image '{os.path.basename(file_path)}' ready to send with next message.",
                parent=self)

        except Exception as e:
            messagebox.showerror("Image Error", f"Failed to load image: {e}", parent=self)
            self.clear_uploaded_image()

    def use_file(self):
        UseFileWindow(self)

    def add_file_context_to_chat(self, file_info):
        """Add file content to chat - handles both text and binary files."""
        try:
            file_path = file_info['path']
            file_type = file_info.get('type', '').lower()

            # Check if it's an image file
            image_extensions = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']
            if file_type in image_extensions:
                try:
                    with open(file_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    mime_type = f"image/{file_type}"
                    self.uploaded_image_data = f"data:{mime_type};base64,{encoded_string}"

                    messagebox.showinfo("Image Loaded",
                        f"Image '{file_info['filename']}' ready to send with next message.",
                        parent=self)
                except Exception as e:
                    messagebox.showerror("Image Error", f"Failed to load image: {e}", parent=self)
            else:
                # Handle as text file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(file_path, 'r', encoding='latin-1') as f:
                            content = f.read()
                    except Exception as e:
                        messagebox.showerror("File Read Error", f"Could not read file: {e}", parent=self)
                        return

                context_text = f"--- Using File: {file_info['filename']} ---\n\n{content}\n\n--- End of File ---"
                self.history.append({"role": "user", "content": context_text})
                self.update_chat_display()

        except Exception as e:
            messagebox.showerror("File Read Error", f"Could not read file: {e}", parent=self)

    def clear_uploaded_image(self):
        self.uploaded_image_data = None

    def create_context_menus(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Copy", command=lambda: self.focus_get().event_generate("<<Copy>>"))
        self.context_menu.add_command(label="Paste", command=lambda: self.prompt_entry.event_generate("<<Paste>>"))
        self.chat_display.bind("<Button-3>", self.show_context_menu)
        self.prompt_entry.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def open_select_profile_window(self):
        SelectProfileWindow(self)

    def apply_profile(self, profile_data, profile_name):
        """Apply a profile and show confirmation in chat."""
        try:
            self.advanced_settings = profile_data.copy()
            self.current_profile_name = profile_name
            self.update_title()
            self.add_system_message(f"✓ Successfully applied profile: {profile_name}")
        except Exception as e:
            self.add_system_message(f"✗ Failed to apply profile '{profile_name}': {str(e)}", is_error=True)

    def add_system_message(self, message, is_error=False):
        """Add a system message to the chat history and update display."""
        system_entry = {
            "role": "system",
            "content": message,
            "is_error": is_error
        }
        self.history.append(system_entry)
        self.update_chat_display()

    def update_title(self):
        self.title(f"Query: {self.config_name} (Profile: {self.current_profile_name})")

    def on_close(self):
        self.app.unregister_query_window(self.config_name)
        self.destroy()

    def send_query_threaded(self, event=None):
        prompt = self.prompt_entry.get("1.0", tk.END).strip()
        if not prompt and not self.uploaded_image_data and not self.history:
            return

        self.prompt_entry.delete("1.0", tk.END)
        self.send_button.config(state=tk.DISABLED)

        if prompt or self.uploaded_image_data:
            user_content_for_history = []
            if prompt:
                user_content_for_history.append({"type": "text", "text": prompt})
            if self.uploaded_image_data:
                user_content_for_history.append({"type": "image_url", "image_url": {"url": self.uploaded_image_data}})
            self.history.append({"role": "user", "content": user_content_for_history})

        self.update_chat_display()
        self.clear_uploaded_image()

        thread = threading.Thread(target=self.call_openrouter_api_with_tool_handling, daemon=True)
        thread.start()

    def call_openrouter_api_with_tool_handling(self):
        """Enhanced version with iteration tracking, detailed tool feedback, and token counting."""
        api_key = self.config_details.get("api_key")
        model_name = self.config_details.get("model")

        if not api_key:
            self.add_system_message("Error: OpenRouter API Key is missing.", is_error=True)
            self.safe_enable_send_button()
            return

        if self.count_tokens_var.get():
            self.token_counter.reset()

        api_url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

        messages = self.history.copy()
        messages = [m for m in messages if m.get('role') != 'system']

        if self.advanced_settings.get("system_message"):
            messages.insert(0, {"role": "system", "content": self.advanced_settings["system_message"]})

        payload = {"model": model_name, "messages": messages}
        try:
            params = OpenRouterAPIParameters(**self.advanced_settings)
            payload.update(params.model_dump(exclude_none=True))
        except Exception as e:
            self.add_system_message(f"Parameter Validation Error: {e}", is_error=True)
            self.safe_enable_send_button()
            return

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            result = response.json()

            if self.count_tokens_var.get():
                self._count_tokens_from_response(result, messages)

            message = result['choices'][0]['message']
            self.history.append(message)

            max_iterations = 30
            iteration = 0

            while message.get("tool_calls") and iteration < max_iterations:
                iteration += 1
                tool_calls = message["tool_calls"]

                self.add_system_message(f"🔧 Tool Call Iteration {iteration}/{max_iterations} - Processing {len(tool_calls)} tool(s)")

                for tool_call in tool_calls:
                    function_name = tool_call['function']['name']
                    self.add_system_message(f"→ Calling tool: {function_name}")

                    if function_name in self.window_tool_registry:
                        try:
                            function_to_call = self.window_tool_registry[function_name]
                            function_args = json.loads(tool_call['function']['arguments'])

                            function_response = None
                            if function_name == "call_agent":
                                function_args['system_message_callback'] = self.add_system_message
                                function_response = function_to_call(**function_args)
                            elif function_name in ["WRITE", "multiedit"] and self.diff_mode_var.get():
                                function_args['diff_callback'] = self.show_diff_popup
                                function_response = function_to_call(**function_args)
                            else:
                                function_response = function_to_call(**function_args)

                            # --- UPDATED SECTION ---
                            if function_name.startswith("todo_"):
                                # If it's a todo tool, format it as HTML
                                todo_html = self._format_todo_html(function_response)
                                self.add_system_message(todo_html) # This content is HTML
                            else:
                                # Otherwise, show the default truncated success message
                                truncated_response = str(function_response)[:200]
                                if len(str(function_response)) > 200:
                                    truncated_response += "..."
                                self.add_system_message(f"✓ Success: {truncated_response}")
                            # --- END UPDATED SECTION ---

                            self.history.append({
                                "tool_call_id": tool_call['id'],
                                "role": "tool",
                                "name": function_name,
                                "content": function_response,
                            })
                        except Exception as e:
                            error_message = f"Error executing tool '{function_name}': {e}"
                            self.add_system_message(f"✗ Failed: {error_message}", is_error=True)

                            self.history.append({
                                "tool_call_id": tool_call['id'],
                                "role": "tool",
                                "name": function_name,
                                "content": error_message,
                            })
                    else:
                        error_message = f"Error: Tool '{function_name}' not found in registry."
                        self.add_system_message(f"✗ {error_message}", is_error=True)

                        self.history.append({
                            "tool_call_id": tool_call['id'],
                            "role": "tool",
                            "name": function_name,
                            "content": error_message,
                        })

                payload['messages'] = [m for m in self.history if m.get('role') != 'system']

                response = requests.post(api_url, headers=headers, json=payload, timeout=180)
                response.raise_for_status()
                result = response.json()

                if self.count_tokens_var.get():
                    self._count_tokens_from_response(result, payload['messages'])

                message = result['choices'][0]['message']
                self.history.append(message)

            if iteration >= max_iterations:
                self.add_system_message(f"⚠ Warning: Reached maximum tool call iterations ({max_iterations})", is_error=True)

            if self.count_tokens_var.get():
                self.add_system_message(self.token_counter.get_summary())

            self.app.root.after(0, self.update_chat_display)

        except requests.exceptions.RequestException as e:
            self.add_system_message(f"API Request Failed: {e}", is_error=True)
        except Exception as e:
            error_msg = f"An unexpected error occurred: {e}"
            self.add_system_message(error_msg, is_error=True)
        finally:
            self.app.root.after(0, self.safe_enable_send_button)

    def update_chat_display(self):
        """Updated to support system messages with proper styling."""

        if self.using_html:
            # HTML rendering path
            html_parts = []

            html_parts.append("""
            <html>
            <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    padding: 12px;
                    background-color: white;
                    line-height: 1.6;
                    margin: 0;
                }
                .code-block-container {
                    position: relative;
                    margin: 10px 0;
                }
                .copy-code-btn {
                    position: absolute;
                    top: 8px;
                    right: 8px;
                    background-color: #e0e0e0;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 0.8em;
                    cursor: pointer;
                    display: none;
                    text-decoration: none;
                    color: black;
                }
                .code-block-container:hover .copy-code-btn {
                    display: block;
                }
                .copy-code-btn:hover {
                    background-color: #d0d0d0;
                }
                .user-message {
                    margin: 10px 0;
                    padding: 10px;
                    background-color: #f0f0f0;
                    border-radius: 8px;
                }
                .user-role {
                    font-weight: bold;
                    color: #333;
                    margin-bottom: 5px;
                }
                .assistant-message {
                    margin: 10px 0;
                    padding: 10px;
                }
                .assistant-role {
                    font-weight: bold;
                    color: #2563eb;
                    margin-bottom: 5px;
                }
                .system-message {
                    font-style: italic;
                    color: #666;
                    font-size: 0.9em;
                    margin: 5px 0;
                    padding: 6px 10px;
                    background-color: #f8f9fa;
                    border-left: 3px solid #6c757d;
                    border-radius: 4px;
                }
                .system-error {
                    color: #dc3545;
                    background-color: #f8d7da;
                    border-left: 3px solid #dc3545;
                }
                h1, h2, h3 {
                    color: #2e6da4;
                    margin-top: 16px;
                    margin-bottom: 8px;
                }
                pre {
                    background: #f5f5f5;
                    padding: 12px;
                    border-radius: 6px;
                    overflow-x: auto;
                    border: 1px solid #ddd;
                }
                code {
                    background: #f0f0f0;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                }
                pre code {
                    background: none;
                    padding: 0;
                }
                ul, ol {
                    margin: 8px 0;
                    padding-left: 24px;
                }
                li {
                    margin: 4px 0;
                }
                blockquote {
                    border-left: 4px solid #ddd;
                    padding-left: 12px;
                    margin: 8px 0;
                    color: #666;
                }
                a {
                    color: #2563eb;
                    text-decoration: none;
                }
                a:hover {
                    text-decoration: underline;
                }
            </style>
            </head>
            <body>
            """)
            # Reset the code blocks dictionary for this render
            self.code_blocks = {}
            code_block_counter = 0

            for item in self.history:
                role = item.get('role')
                content = item.get('content')

                if role == 'system':
                    is_error = item.get('is_error', False)
                    css_class = 'system-message system-error' if is_error else 'system-message'
                    # --- MODIFICATION ---
                    # If content is HTML (our todo list), don't escape it.
                    is_html_content = str(content).strip().startswith('<div')
                    if is_html_content:
                        html_parts.append(f'<div class="{css_class}">{content}</div>')
                    else:
                        escaped_text = str(content).replace('<', '&lt;').replace('>', '&gt;')
                        html_parts.append(f'<div class="{css_class}">{escaped_text}</div>')
                    # --- END MODIFICATION ---

                elif role == 'user':
                    html_parts.append('<div class="user-message">')
                    html_parts.append('<div class="user-role">You:</div>')
                    user_content = ""
                    if isinstance(content, list):
                        for part in content:
                            if part['type'] == 'text':
                                user_content += part['text']
                    else:
                        user_content = str(content)

                    # Convert markdown in user messages to HTML
                    try:
                        from markdown import markdown
                        # Use a simpler markdown conversion for user messages
                        html_content = markdown(
                            user_content,
                            extensions=['fenced_code', 'codehilite', 'nl2br']
                        )
                        processed_html, code_block_counter = self._process_html_for_code_blocks(
                            html_content, code_block_counter
                        )
                        html_parts.append(processed_html)

                    except ImportError:
                        html_parts.append(f'<div>{self._escape_html(user_content).replace(chr(10), "<br>")}</div>')

                    html_parts.append('</div>')
                elif role == 'assistant':
                    if content:
                        html_parts.append('<div class="assistant-message">')
                        html_parts.append('<div class="assistant-role">Assistant:</div>')

                        try:
                            from markdown import markdown
                            html_content = markdown(
                                content,
                                extensions=[
                                    'fenced_code',
                                    'codehilite',
                                    'tables',
                                    'nl2br',
                                    'sane_lists'
                                ]
                            )
                            processed_html, code_block_counter = self._process_html_for_code_blocks(
                                html_content, code_block_counter
                            )
                            html_parts.append(processed_html)

                        except ImportError:
                            escaped = self._escape_html(content).replace('\n', '<br>')
                            html_parts.append(escaped)

                        html_parts.append('</div>')

            html_parts.append('</body></html>')
            full_html = ''.join(html_parts)

            try:
                self.chat_display.load_html(full_html)
                self.app.root.after(100, self.scroll_to_bottom)
            except Exception as e:
                print(f"Error loading HTML: {e}")

        else:
            # Text widget fallback
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete("1.0", tk.END)

            self.chat_display.tag_configure("system", font=("Arial", 9, "italic"), foreground="#666", background="#f8f9fa")
            self.chat_display.tag_configure("system_error", font=("Arial", 9, "italic"), foreground="#dc3545", background="#f8d7da")

            for item in self.history:
                role = item.get('role')
                content = item.get('content')

                if role == 'system':
                    # --- MODIFICATION ---
                    # Don't show HTML in text-mode fallback, just a note.
                    is_html_content = str(content).strip().startswith('<div')
                    if is_html_content:
                        content_to_display = "[Todo List Update]"
                    else:
                        content_to_display = content
                    
                    is_error = item.get('is_error', False)
                    tag = 'system_error' if is_error else 'system'
                    self.chat_display.insert(tk.END, f"{content_to_display}\n", tag)
                    # --- END MODIFICATION ---

                elif role == 'user':
                    self.append_to_chat_display("You: ", "user_role")
                    if isinstance(content, list):
                        for part in content:
                            if part['type'] == 'text':
                                self.append_to_chat_display(f"{part['text']}\n")
                            elif part['type'] == 'image_url':
                                self.append_to_chat_display("[Image]\n", "system")
                    else:
                        self.append_to_chat_display(f"{content}\n")

                elif role == 'assistant':
                    if content:
                        self.append_to_chat_display("Assistant: ", "assistant_role")

                        try:
                            self.markdown_renderer.render(content)
                        except Exception as e:
                            print(f"Markdown rendering error: {e}")
                            self.chat_display.insert(tk.END, content)

                        self.chat_display.insert(tk.END, "\n")

            self.chat_display.config(state=tk.DISABLED)
            self.chat_display.see(tk.END)

    def append_to_chat_display(self, text, tag=None):
        """Append text to chat display - works with both HtmlFrame and Text widget."""

        if self.using_html:
            self.update_chat_display()
        else:
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.tag_configure("user_role", font=("Arial", 11, "bold"))
            self.chat_display.tag_configure("assistant_role", font=("Arial", 11, "bold"), foreground="blue")
            self.chat_display.tag_configure("system", font=("Arial", 9, "italic"), foreground="gray")
            self.chat_display.tag_configure("error", font=("Arial", 10, "italic"), foreground="red")
            self.chat_display.insert(tk.END, text, tag)
            self.chat_display.config(state=tk.DISABLED)
            self.chat_display.see(tk.END)
