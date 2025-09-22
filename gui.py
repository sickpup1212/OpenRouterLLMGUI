import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, Toplevel, Text, filedialog
import threading
import time
import json
import os
import re
import requests
import base64
import shutil
from io import BytesIO
from pynput import keyboard
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union, Literal, Any
from enum import Enum


# --- Important Notes ---
# This application now requires the 'Pillow' library for image processing.
# Please install it using pip:
# pip install Pillow
#
# It also uses 'pynput' and 'requests'. Install with:
# pip install pynput requests
#
# It also uses 'pydantic'. Install with:
# pip install pydantic

try:
    from PIL import Image, ImageTk
except ImportError:
    messagebox.showerror("Missing Dependency", "Pillow library not found. Please run 'pip install Pillow'")
    exit()


class VerbosityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResponseFormat(BaseModel):
    type: Literal["json_object"]


class ToolFunction(BaseModel):
    name: str


class ToolChoice(BaseModel):
    type: Literal["function"]
    function: ToolFunction


class OpenRouterAPIParameters(BaseModel):
    """
    Pydantic model for OpenRouter API parameters.
    This model includes all the sampling parameters that can be used
    to configure OpenRouter API requests for language model generation.
    """
    temperature: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Controls variety in responses. Lower = more predictable, higher = more diverse"
    )
    top_p: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling - limits model choices to top tokens with cumulative probability P"
    )
    top_k: Optional[int] = Field(
        default=0,
        ge=0,
        description="Limits model choice to top K tokens at each step. 0 = disabled"
    )
    frequency_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Reduces repetition based on token frequency in input"
    )
    presence_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Reduces repetition of tokens already used in input"
    )
    repetition_penalty: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Reduces repetition from input. Higher = less repetition"
    )
    min_p: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum probability for token consideration, relative to most likely token"
    )
    top_a: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Dynamic filtering based on probability of most likely token"
    )
    seed: Optional[int] = Field(
        default=None,
        description="Seed for deterministic sampling"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of tokens to generate"
    )
    logit_bias: Optional[Dict[str, float]] = Field(
        default=None,
        description="Map of token IDs to bias values (-100 to 100)"
    )
    logprobs: Optional[bool] = Field(
        default=None,
        description="Whether to return log probabilities of output tokens"
    )
    top_logprobs: Optional[int] = Field(
        default=None,
        ge=0,
        le=20,
        description="Number of most likely tokens to return with log probabilities"
    )
    response_format: Optional[ResponseFormat] = Field(
        default=None,
        description="Forces specific output format, e.g., JSON mode"
    )
    structured_outputs: Optional[bool] = Field(
        default=None,
        description="Whether model can return structured outputs using response_format json_schema"
    )
    stop: Optional[List[str]] = Field(
        default=None,
        description="Array of tokens that will stop generation"
    )
    tools: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Tool calling parameter following OpenAI's tool calling format"
    )
    tool_choice: Optional[Union[str, ToolChoice]] = Field(
        default=None,
        description="Controls which tool is called: 'none', 'auto', 'required', or specific tool"
    )
    parallel_tool_calls: Optional[bool] = Field(
        default=True,
        description="Whether to enable parallel function calling during tool use"
    )
    verbosity: Optional[VerbosityLevel] = Field(
        default=VerbosityLevel.MEDIUM,
        description="Controls verbosity and length of model response"
    )
    reasoning: Optional[ReasoningLevel] = Field(
        default=None,
        description="Controls the reasoning level of model response"
    )


class SelectProfileWindow(Toplevel):
    """A window to select a saved LLM configuration profile."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Select Configuration Profile")
        self.transient(parent)
        self.geometry("400x300")
        self.parent = parent
        self.app = parent.app
        self.profiles = self.app.llm_profiles

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Select a profile to apply:").pack(anchor="w", pady=(0, 5))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.profile_listbox = tk.Listbox(list_frame)
        self.profile_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for name in self.profiles.keys():
            self.profile_listbox.insert(tk.END, name)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.profile_listbox.yview)
        self.profile_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Apply", command=self.apply_selection).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def apply_selection(self):
        selected_indices = self.profile_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select a profile.", parent=self)
            return

        profile_name = self.profile_listbox.get(selected_indices[0])
        profile_data = self.profiles.get(profile_name)

        if profile_data:
            self.parent.apply_profile(profile_data, profile_name)
            self.destroy()
        else:
            messagebox.showerror("Error", f"Could not find profile '{profile_name}'.", parent=self)


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
        self.history = [] # For conversation history

        self.create_widgets(initial_prompt, initial_response)
        self.create_context_menus()
        self.update_title()

    def create_widgets(self, initial_prompt, initial_response):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)

        top_bar = ttk.Frame(main_frame)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(top_bar, text="New Conversation", command=self.start_new_conversation).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_bar, text="Load Profile", command=self.open_select_profile_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="Upload Image", command=self.upload_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="Use File", command=self.use_file).pack(side=tk.LEFT, padx=5)

        save_menu_button = ttk.Menubutton(top_bar, text="Save")
        save_menu = tk.Menu(save_menu_button, tearoff=0)
        save_menu.add_command(label="Save Last Prompt", command=self.save_prompt)
        save_menu.add_command(label="Save Last Response", command=self.save_response)
        save_menu.add_command(label="Save Full History", command=self.save_both)
        save_menu_button['menu'] = save_menu
        save_menu_button.pack(side=tk.LEFT, padx=5)

        chat_frame = ttk.Frame(main_frame)
        chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.rowconfigure(0, weight=1)
        chat_frame.columnconfigure(0, weight=1)

        self.chat_display = Text(chat_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Arial", 11))
        self.chat_display.grid(row=0, column=0, sticky="nsew")
        chat_scrollbar = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self.chat_display.yview)
        chat_scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_display['yscrollcommand'] = chat_scrollbar.set

        input_frame = ttk.Frame(main_frame)
        input_frame.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        input_frame.columnconfigure(0, weight=1)

        self.prompt_entry = Text(input_frame, height=3, font=("Arial", 10))
        self.prompt_entry.grid(row=0, column=0, sticky="ew")
        self.prompt_entry.bind("<Return>", self.send_on_enter)
        self.prompt_entry.bind("<Shift-Return>", self.insert_newline)

        ttk.Button(input_frame, text="Send", command=self.send_query_threaded).grid(row=0, column=1, padx=(5, 0))

        self.prompt_entry.focus_set()

        if initial_prompt: self.prompt_entry.insert("1.0", initial_prompt)
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
        self.history = []
        self.clear_uploaded_image()
        self.update_chat_display()
        self.prompt_entry.delete("1.0", tk.END)
        self.append_to_chat_display("--- New conversation started ---\n", "system")

    def save_prompt(self):
        last_user_prompt = next((item['content'] for item in reversed(self.history) if item['role'] == 'user'), None)
        if not last_user_prompt:
            messagebox.showwarning("Save Error", "No prompt found in history.", parent=self)
            return
        self.app.add_saved_item("Prompt", self.config_details['model'], last_user_prompt, "")
        messagebox.showinfo("Success", "Last prompt saved.", parent=self)

    def save_response(self):
        last_assistant_response = next((item['content'] for item in reversed(self.history) if item['role'] == 'assistant'), None)
        if not last_assistant_response:
            messagebox.showwarning("Save Error", "No response found in history.", parent=self)
            return
        self.app.add_saved_item("Response", self.config_details['model'], "", last_assistant_response)
        messagebox.showinfo("Success", "Last response saved.", parent=self)

    def save_both(self):
        full_history_text = self.chat_display.get("1.0", tk.END).strip()
        if not full_history_text:
            messagebox.showwarning("Save Error", "History is empty.", parent=self)
            return
        self.app.add_saved_item("History", self.config_details['model'], full_history_text, "")
        messagebox.showinfo("Success", "Full conversation history saved.", parent=self)

    def upload_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.gif")])
        if not file_path: return
        try:
            with open(file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            mime_type = f"image/{file_path.split('.')[-1]}"
            self.uploaded_image_data = f"data:{mime_type};base64,{encoded_string}"
            self.append_to_chat_display(f"[Image Uploaded: {os.path.basename(file_path)}]\n", "system")
        except Exception as e:
            messagebox.showerror("Image Error", f"Failed to load image: {e}")
            self.clear_uploaded_image()

    def use_file(self):
        UseFileWindow(self)

    def add_file_context_to_chat(self, file_info):
        try:
            with open(file_info['path'], 'r', encoding='utf-8') as f:
                content = f.read()
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
        self.advanced_settings = profile_data.copy()
        self.current_profile_name = profile_name
        self.update_title()
        self.append_to_chat_display(f"--- Applied settings profile: {profile_name} ---\n", "system")

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

        if prompt or self.uploaded_image_data:
            user_content_for_history = []
            if prompt: user_content_for_history.append({"type": "text", "text": prompt})
            if self.uploaded_image_data: user_content_for_history.append({"type": "image_url", "image_url": {"url": self.uploaded_image_data}})
            self.history.append({"role": "user", "content": user_content_for_history})

        self.update_chat_display()
        self.clear_uploaded_image()

        thread = threading.Thread(target=self.call_openrouter_api, daemon=True)
        thread.start()

    def call_openrouter_api(self):
        api_key = self.config_details.get("api_key")
        model_name = self.config_details.get("model")
        if not api_key:
            self.append_to_chat_display("Error: OpenRouter API Key is missing.", "error")
            return

        api_url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

        messages = self.history.copy()
        if self.advanced_settings.get("system_message"):
            messages.insert(0, {"role": "system", "content": self.advanced_settings["system_message"]})

        payload = {"model": model_name, "messages": messages}

        # Use Pydantic model to structure and validate parameters
        try:
            params = OpenRouterAPIParameters(**self.advanced_settings)
            payload.update(params.model_dump(exclude_none=True))
        except Exception as e:
            self.append_to_chat_display(f"Parameter Validation Error: {e}", "error")
            return

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            result = response.json()
            text_response = result['choices'][0]['message']['content']
            self.history.append({"role": "assistant", "content": text_response})
            self.update_chat_display()
        except requests.exceptions.RequestException as e:
            self.append_to_chat_display(f"API Request Failed: {e}", "error")
        except Exception as e:
            self.append_to_chat_display(f"An unexpected error occurred: {e}\n\nFull Response:\n{getattr(e, 'response', '')}", "error")

    def update_chat_display(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        for item in self.history:
            role = item['role']
            content = item['content']
            if role == 'user':
                self.append_to_chat_display("You: ", "user_role")
                if isinstance(content, list):
                    for part in content:
                        if part['type'] == 'text': self.append_to_chat_display(f"{part['text']}\n")
                        elif part['type'] == 'image_url': self.append_to_chat_display("[Image]\n", "system")
                else: self.append_to_chat_display(f"{content}\n")
            elif role == 'assistant':
                self.append_to_chat_display("Assistant: ", "assistant_role")
                self.append_to_chat_display(f"{content}\n\n")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def append_to_chat_display(self, text, tag=None):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.tag_configure("user_role", font=("Arial", 11, "bold"))
        self.chat_display.tag_configure("assistant_role", font=("Arial", 11, "bold"), foreground="blue")
        self.chat_display.tag_configure("system", font=("Arial", 9, "italic"), foreground="gray")
        self.chat_display.tag_configure("error", font=("Arial", 10, "italic"), foreground="red")
        self.chat_display.insert(tk.END, text, tag)
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)


class UseFileWindow(Toplevel):
    """Window to select a saved file to use in a chat."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Use a Saved File")
        self.transient(parent)
        self.geometry("600x400")
        self.parent = parent
        self.app = parent.app

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ('filename', 'type', 'date_added')
        self.files_tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        self.files_tree.heading('filename', text='Filename')
        self.files_tree.heading('type', text='Type')
        self.files_tree.heading('date_added', text='Date Added')
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        self.files_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for i, item in enumerate(self.app.files):
            self.files_tree.insert('', tk.END, iid=i, values=(item['filename'], item['type'], item['date_added']))

        use_button = ttk.Button(main_frame, text="Use Selected File", command=self.use_selected)
        use_button.pack()

    def use_selected(self):
        selected_iid = self.files_tree.focus()
        if not selected_iid:
            messagebox.showwarning("Selection Error", "Please select a file to use.", parent=self)
            return

        item_index = int(selected_iid)
        file_info = self.app.files[item_index]
        self.parent.add_file_context_to_chat(file_info)
        self.destroy()


class DesktopUtilitiesApp:
    CONFIG_FILE = "config.json"
    FILES_DIR = "saved_files"

    def __init__(self, root):
        self.root = root
        self.root.title("Desktop Utilities")
        self.root.geometry("950x800") # Increased window size

        self.shortcuts = {}
        self.llm_configs = {}
        self.llm_profiles = {}
        self.saved_items = []
        self.files = []
        self.open_query_windows = {}
        self.openrouter_models = []
        self.models_data = []

        self.buffer = ""
        self.keyboard_controller = keyboard.Controller()

        self.setup_directories()
        self.load_data()
        self.create_widgets()
        self.start_listener()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_directories(self):
        if not os.path.exists(self.FILES_DIR):
            os.makedirs(self.FILES_DIR)

    def load_data(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    shortcuts_data = data.get("shortcuts", {})
                    for trigger, details in shortcuts_data.items():
                        self.shortcuts[trigger] = {
                            "output": details["output"],
                            "enabled": tk.BooleanVar(value=details.get("enabled", True))
                        }
                    self.llm_configs = data.get("llm_configs", {})
                    self.llm_profiles = data.get("llm_profiles", {})
                    self.saved_items = data.get("saved_items", [])
                    self.files = data.get("files", [])
            except json.JSONDecodeError:
                messagebox.showerror("Config Error", "Failed to load config.json. It might be corrupted.")

    def save_data(self):
        shortcuts_to_save = {
            trigger: {"output": details["output"], "enabled": details["enabled"].get()}
            for trigger, details in self.shortcuts.items()
        }
        data = {
            "shortcuts": shortcuts_to_save,
            "llm_configs": self.llm_configs,
            "llm_profiles": self.llm_profiles,
            "saved_items": self.saved_items,
            "files": self.files
        }
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)

    def on_closing(self):
        self.save_data()
        self.root.destroy()

    def create_widgets(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(expand=True, fill='both', padx=10, pady=10)

        shortcut_tab = ttk.Frame(notebook)
        llm_tab = ttk.Frame(notebook)
        profiles_tab = ttk.Frame(notebook)
        saved_items_tab = ttk.Frame(notebook)
        files_tab = ttk.Frame(notebook)

        notebook.add(shortcut_tab, text='Text Shortcuts')
        notebook.add(llm_tab, text='LLM Models')
        notebook.add(profiles_tab, text='LLM Profiles')
        notebook.add(saved_items_tab, text='Saved Items')
        notebook.add(files_tab, text='Files')

        self.create_shortcut_tab(shortcut_tab)
        self.create_llm_tab(llm_tab)
        self.create_config_profiles_tab(profiles_tab)
        self.create_saved_items_tab(saved_items_tab)
        self.create_files_tab(files_tab)

    def create_shortcut_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = ttk.LabelFrame(main_frame, text="Create New Shortcut", padding="10")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)
        ttk.Label(input_frame, text="Trigger:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.trigger_entry = ttk.Entry(input_frame, width=30)
        self.trigger_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(input_frame, text="Output:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.output_entry = ttk.Entry(input_frame, width=50)
        self.output_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(input_frame, text="Add Shortcut", command=self.add_shortcut).grid(row=2, column=1, padx=5, pady=10, sticky="e")
        self.shortcut_list_frame = ttk.LabelFrame(main_frame, text="Your Shortcuts", padding="10")
        self.shortcut_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.update_shortcut_list_ui()

    def add_shortcut(self):
        trigger = self.trigger_entry.get()
        output = self.output_entry.get()
        if not trigger or not output:
            messagebox.showwarning("Input Error", "Both Trigger and Output fields are required.")
            return
        if trigger in self.shortcuts:
            messagebox.showerror("Duplicate Error", f"The trigger '{trigger}' already exists.")
            return
        self.shortcuts[trigger] = {"output": output, "enabled": tk.BooleanVar(value=True)}
        self.trigger_entry.delete(0, tk.END)
        self.output_entry.delete(0, tk.END)
        self.update_shortcut_list_ui()

    def update_shortcut_list_ui(self):
        for widget in self.shortcut_list_frame.winfo_children():
            widget.destroy()
        for i, (trigger, data) in enumerate(self.shortcuts.items()):
            ttk.Checkbutton(self.shortcut_list_frame, variable=data["enabled"]).grid(row=i, column=0, padx=5, sticky="w")
            label_text = f"'{trigger}' -> '{data['output'][:30]}...'" if len(data['output']) > 30 else f"'{trigger}' -> '{data['output']}'"
            ttk.Label(self.shortcut_list_frame, text=label_text).grid(row=i, column=1, padx=5, sticky="w")
            ttk.Button(self.shortcut_list_frame, text="Delete", command=lambda t=trigger: self.delete_shortcut(t)).grid(row=i, column=2, padx=5, sticky="e")
        self.shortcut_list_frame.columnconfigure(1, weight=1)

    def delete_shortcut(self, trigger):
        if trigger in self.shortcuts:
            del self.shortcuts[trigger]
            self.update_shortcut_list_ui()

    def create_llm_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = ttk.LabelFrame(main_frame, text="New LLM Model Configuration", padding="10")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)
        ttk.Label(input_frame, text="Config Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.llm_name_entry = ttk.Entry(input_frame)
        self.llm_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(input_frame, text="OpenRouter API Key:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.llm_api_key_entry = ttk.Entry(input_frame, show="*")
        self.llm_api_key_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(input_frame, text="Model:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.llm_model_combo = ttk.Combobox(input_frame, state="readonly")
        self.llm_model_combo.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        refresh_button = ttk.Button(input_frame, text="Refresh Models", command=self.fetch_openrouter_models_threaded)
        refresh_button.grid(row=2, column=2, padx=5)
        ttk.Button(input_frame, text="Save Configuration", command=self.add_llm_config).grid(row=3, column=1, padx=5, pady=10, sticky="e")
        self.llm_list_frame = ttk.LabelFrame(main_frame, text="Your LLM Model Configurations", padding="10")
        self.llm_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.update_llm_list_ui()
        self.fetch_openrouter_models_threaded()

    def fetch_openrouter_models_threaded(self):
        self.llm_model_combo.set("Fetching models...")
        thread = threading.Thread(target=self.fetch_openrouter_models, daemon=True)
        thread.start()

    def fetch_openrouter_models(self):
        try:
            response = requests.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            self.models_data = response.json()['data']
            self.openrouter_models = sorted([model['id'] for model in self.models_data])

            def update_ui():
                self.llm_model_combo['values'] = self.openrouter_models
                self.llm_model_combo.set("Select a model")
                if hasattr(self, 'profile_model_combo'):
                    self.profile_model_combo['values'] = self.openrouter_models
                    self.profile_model_combo.set("Select a model to see parameters")

            self.root.after(0, update_ui)
        except requests.exceptions.RequestException as e:
            self.root.after(0, lambda: messagebox.showerror("API Error", f"Failed to fetch models from OpenRouter: {e}"))
            self.root.after(0, lambda: self.llm_model_combo.set("Failed to fetch models"))

    def add_llm_config(self):
        name = self.llm_name_entry.get()
        api_key = self.llm_api_key_entry.get()
        model = self.llm_model_combo.get()
        if not all([name, api_key, model]) or model == "Select a model":
            messagebox.showwarning("Input Error", "All fields, including a selected model, are required.")
            return
        if name in self.llm_configs:
            messagebox.showerror("Duplicate Error", f"The configuration name '{name}' already exists.")
            return
        self.llm_configs[name] = {"api_key": api_key, "model": model}
        self.llm_name_entry.delete(0, tk.END)
        self.llm_api_key_entry.delete(0, tk.END)
        self.llm_model_combo.set("Select a model")
        self.update_llm_list_ui()

    def update_llm_list_ui(self):
        for widget in self.llm_list_frame.winfo_children():
            widget.destroy()
        for i, (name, data) in enumerate(self.llm_configs.items(), 1):
            trigger_text = f"Trigger: __" + str(i)
            label_text = f"{name} (Model: {data.get('model', 'N/A')})"
            ttk.Label(self.llm_list_frame, text=label_text).grid(row=i, column=0, padx=5, sticky="w")
            ttk.Label(self.llm_list_frame, text=trigger_text).grid(row=i, column=1, padx=10, sticky="w")
            button_frame = ttk.Frame(self.llm_list_frame)
            button_frame.grid(row=i, column=2, sticky='e')
            ttk.Button(button_frame, text="Query", command=lambda n=name: self.show_query_window(n)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Delete", command=lambda n=name: self.delete_llm_config(n)).pack(side=tk.LEFT, padx=2)
        self.llm_list_frame.columnconfigure(0, weight=1)
        self.llm_list_frame.columnconfigure(2, weight=1)

    def delete_llm_config(self, name):
        if name in self.llm_configs:
            del self.llm_configs[name]
            self.update_llm_list_ui()

    def create_config_profiles_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(1, weight=1)

        editor_frame = ttk.LabelFrame(main_frame, text="Create/Edit Profile", padding="10")
        editor_frame.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        editor_frame.columnconfigure(1, weight=1)

        # Model selection for profile
        ttk.Label(editor_frame, text="Model:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.profile_model_combo = ttk.Combobox(editor_frame, state="readonly")
        self.profile_model_combo.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        self.profile_model_combo.bind("<<ComboboxSelected>>", self.on_profile_model_select)

        ttk.Label(editor_frame, text="Profile Name:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.profile_name_entry = ttk.Entry(editor_frame)
        self.profile_name_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        # --- All parameters from the image ---
        fields = [
            ("System Message", "system_message", "", "text"),
            ("Tools", "tools", "", "entry"),
            ("Temperature", "temperature", 1.0, "spinbox_float"),
            ("Top P", "top_p", 1.0, "spinbox_float"),
            ("Top K", "top_k", 0, "spinbox_int"),
            ("Min P", "min_p", 0.0, "spinbox_float"),
            ("Top A", "top_a", 0.0, "spinbox_float"),
            ("Frequency Penalty", "frequency_penalty", 0.0, "spinbox_float"),
            ("Presence Penalty", "presence_penalty", 0.0, "spinbox_float"),
            ("Repetition Penalty", "repetition_penalty", 1.0, "spinbox_float"),
            ("Max Tokens", "max_tokens", 1024, "spinbox_int"),
            ("Logit Bias", "logit_bias", "", "entry"),
            ("Top Logprobs", "top_logprobs", 0, "spinbox_int"),
            ("Seed", "seed", 0, "spinbox_int"),
            ("Response Format", "response_format", "", "entry"),
            ("Structured Outputs", "structured_outputs", "", "entry"),
            ("Stop Sequences", "stop", "", "entry"),
            ("Reasoning", "reasoning", "", "entry"),
            ("Verbosity", "verbosity", 0, "spinbox_int"),
        ]

        self.profile_entries = {}
        row_counter = 2
        for label, key, default, widget_type in fields:
            ttk.Label(editor_frame, text=f"{label}:").grid(row=row_counter, column=0, padx=5, pady=2, sticky="w")

            if widget_type == "text":
                widget = Text(editor_frame, height=3, width=30)
            elif widget_type == "entry":
                widget = ttk.Entry(editor_frame)
            elif widget_type == "spinbox_float":
                widget = ttk.Spinbox(editor_frame, from_=0.0, to=2.0, increment=0.1, format="%.1f", width=10)
                widget.set(default)
            elif widget_type == "spinbox_int":
                widget = ttk.Spinbox(editor_frame, from_=0, to=8192, width=10)
                widget.set(default)

            widget.grid(row=row_counter, column=1, columnspan=2, padx=5, pady=2, sticky="ew")
            self.profile_entries[key] = widget
            row_counter += 1

        # --- Checkbuttons for boolean parameters ---
        bool_fields = [
            ("Logprobs", "logprobs"),
            ("Parallel Tool Calls", "parallel_tool_calls"),
            ("Include Reasoning", "include_reasoning"),
        ]

        for label, key in bool_fields:
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(editor_frame, text=label, variable=var)
            chk.grid(row=row_counter, column=0, columnspan=3, padx=5, pady=2, sticky="w")
            self.profile_entries[key] = var # Store the variable
            row_counter += 1
            
        # Initially disable all fields
        self.toggle_profile_fields(False)

        save_button = ttk.Button(editor_frame, text="Save Profile", command=self.add_llm_profile)
        save_button.grid(row=row_counter, column=0, columnspan=3, pady=10)

        list_frame = ttk.LabelFrame(main_frame, text="Saved Profiles", padding="10")
        list_frame.grid(row=0, column=1, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.profiles_tree = ttk.Treeview(list_frame, columns=('name',), show='headings')
        self.profiles_tree.heading('name', text='Profile Name')
        self.profiles_tree.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.profiles_tree.bind('<<TreeviewSelect>>', self.load_profile_for_editing)

        delete_button = ttk.Button(list_frame, text="Delete Selected", command=self.delete_llm_profile)
        delete_button.pack()

        self.update_llm_profiles_ui()

    def get_model_parameters(self, model_name):
        """Get supported parameters for a specific model"""
        for model in self.models_data:
            if model['id'] == model_name:
                return model.get('supported_parameters')
        return None

    def on_profile_model_select(self, event=None):
        selected_model = self.profile_model_combo.get()
        if not selected_model or selected_model == "Select a model to see parameters":
            self.toggle_profile_fields(False)
            return

        supported_params = self.get_model_parameters(selected_model)
        if supported_params is None:
            messagebox.showinfo("Info", "This model does not specify supported parameters. All parameters are enabled.", parent=self.root)
            self.toggle_profile_fields(True)
        else:
            self.toggle_profile_fields(True, supported_params)

    def toggle_profile_fields(self, enable, supported_params=None):
        for key, widget in self.profile_entries.items():
            if enable:
                if supported_params is None or key in supported_params:
                    if isinstance(widget, tk.BooleanVar):
                        # Checkbuttons don't have a state property in the same way
                        pass
                    else:
                        widget.config(state=tk.NORMAL)
                else:
                    if not isinstance(widget, tk.BooleanVar):
                        widget.config(state=tk.DISABLED)
            else:
                if not isinstance(widget, tk.BooleanVar):
                    widget.config(state=tk.DISABLED)

    def add_llm_profile(self):
        profile_name = self.profile_name_entry.get().strip()
        model_name = self.profile_model_combo.get()
        if not profile_name:
            messagebox.showwarning("Input Error", "Profile Name cannot be empty.", parent=self.root)
            return
        if not model_name or model_name == "Select a model to see parameters":
            messagebox.showwarning("Input Error", "Please select a model for the profile.", parent=self.root)
            return

        if profile_name in self.llm_profiles and not messagebox.askyesno("Confirm Overwrite", f"A profile named '{profile_name}' already exists. Do you want to overwrite it?"):
            return

        settings = {"model": model_name}
        for key, widget in self.profile_entries.items():
            # Only save enabled fields
            if not isinstance(widget, tk.BooleanVar) and widget.cget('state') == tk.DISABLED:
                continue

            if isinstance(widget, tk.BooleanVar):
                value = widget.get()
            elif isinstance(widget, Text):
                value = widget.get("1.0", tk.END).strip()
            else: # Entry or Spinbox
                value = widget.get().strip()

            if value or isinstance(value, bool): # Store if not empty or is a boolean
                try:
                    if isinstance(widget, ttk.Spinbox):
                        value = float(value) if "." in str(widget.cget('format')) else int(value)
                    settings[key] = value
                except (ValueError, TypeError):
                    if value: settings[key] = value

        self.llm_profiles[profile_name] = settings
        self.update_llm_profiles_ui()
        messagebox.showinfo("Success", f"Profile '{profile_name}' saved.", parent=self.root)

    def delete_llm_profile(self):
        selected_item = self.profiles_tree.focus()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Please select a profile to delete.", parent=self.root)
            return

        profile_name = self.profiles_tree.item(selected_item)['values'][0]
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the profile '{profile_name}'?"):
            if profile_name in self.llm_profiles:
                del self.llm_profiles[profile_name]
                self.update_llm_profiles_ui()

    def update_llm_profiles_ui(self):
        self.profiles_tree.delete(*self.profiles_tree.get_children())
        for name in sorted(self.llm_profiles.keys()):
            self.profiles_tree.insert('', tk.END, values=(name,))

    def load_profile_for_editing(self, event=None):
        selected_item = self.profiles_tree.focus()
        if not selected_item: return

        profile_name = self.profiles_tree.item(selected_item)['values'][0]
        profile_data = self.llm_profiles.get(profile_name, {})

        model_name = profile_data.get("model")
        if model_name and model_name in self.openrouter_models:
            self.profile_model_combo.set(model_name)
            self.on_profile_model_select()
        else:
            self.profile_model_combo.set("Select a model to see parameters")
            self.toggle_profile_fields(False)


        self.profile_name_entry.delete(0, tk.END)
        self.profile_name_entry.insert(0, profile_name)

        for key, widget in self.profile_entries.items():
            value = profile_data.get(key, "")
            if isinstance(widget, tk.BooleanVar):
                widget.set(bool(value))
            elif isinstance(widget, Text):
                widget.delete("1.0", tk.END)
                widget.insert("1.0", str(value))
            elif isinstance(widget, ttk.Entry):
                widget.delete(0, tk.END)
                widget.insert(0, str(value))
            else: # Spinbox
                widget.set(str(value) if value else "0")

    def create_saved_items_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('timestamp', 'type', 'model', 'content')
        self.saved_items_tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        self.saved_items_tree.heading('timestamp', text='Timestamp')
        self.saved_items_tree.heading('type', text='Type')
        self.saved_items_tree.heading('model', text='Model')
        self.saved_items_tree.heading('content', text='Content')
        self.saved_items_tree.column('timestamp', width=150, anchor=tk.W)
        self.saved_items_tree.column('type', width=80, anchor=tk.W)
        self.saved_items_tree.column('model', width=200, anchor=tk.W)
        self.saved_items_tree.column('content', width=300, anchor=tk.W)
        self.saved_items_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.saved_items_tree.yview)
        self.saved_items_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        action_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
        action_frame.pack(fill=tk.X)
        use_button = ttk.Button(action_frame, text="Use Selected", command=self.use_selected_saved_item)
        use_button.pack(side=tk.LEFT, padx=(0, 5))
        delete_button = ttk.Button(action_frame, text="Delete Selected", command=self.delete_selected_saved_item)
        delete_button.pack(side=tk.LEFT)
        self.update_saved_items_ui()

    def update_saved_items_ui(self):
        self.saved_items_tree.delete(*self.saved_items_tree.get_children())
        for i, item in enumerate(self.saved_items):
            content_preview = (item.get('prompt', '') + item.get('response', ''))[:75].replace('\n', ' ') + "..."
            values = (item.get('timestamp', ''), item.get('type', ''), item.get('model', ''), content_preview)
            self.saved_items_tree.insert('', tk.END, iid=i, values=values)

    def add_saved_item(self, item_type, model, prompt, response):
        new_item = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "type": item_type, "model": model, "prompt": prompt, "response": response}
        self.saved_items.append(new_item)
        self.update_saved_items_ui()

    def delete_selected_saved_item(self):
        selected_iid = self.saved_items_tree.focus()
        if not selected_iid:
            messagebox.showwarning("Selection Error", "Please select an item to delete.")
            return
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete the selected item?"):
            item_index = int(selected_iid)
            del self.saved_items[item_index]
            self.update_saved_items_ui()

    def use_selected_saved_item(self):
        selected_iid = self.saved_items_tree.focus()
        if not selected_iid:
            messagebox.showwarning("Selection Error", "Please select an item to use.")
            return
        item_index = int(selected_iid)
        item_to_use = self.saved_items[item_index]
        model_to_find = item_to_use.get('model')
        found_config_name = None
        for name, config in self.llm_configs.items():
            if config.get('model') == model_to_find:
                found_config_name = name
                break
        if not found_config_name:
            messagebox.showerror("Not Found", f"No LLM configuration found for model '{model_to_find}'. Please create one first.")
            return
        self.show_query_window(found_config_name, initial_prompt=item_to_use.get('prompt', ''), initial_response=item_to_use.get('response', ''))

    def create_files_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('filename', 'type', 'date_added')
        self.files_tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        self.files_tree.heading('filename', text='Filename')
        self.files_tree.heading('type', text='Type')
        self.files_tree.heading('date_added', text='Date Added')
        self.files_tree.column('filename', width=300, anchor=tk.W)
        self.files_tree.column('type', width=100, anchor=tk.W)
        self.files_tree.column('date_added', width=150, anchor=tk.W)
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        self.files_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        action_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="Add File", command=self.add_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="Delete Selected File", command=self.delete_selected_file).pack(side=tk.LEFT)
        self.update_files_ui()

    def update_files_ui(self):
        self.files_tree.delete(*self.files_tree.get_children())
        for i, item in enumerate(self.files):
            values = (item['filename'], item['type'], item['date_added'])
            self.files_tree.insert('', tk.END, iid=i, values=values)

    def add_file(self):
        source_path = filedialog.askopenfilename()
        if not source_path: return

        filename = os.path.basename(source_path)
        dest_path = os.path.join(self.FILES_DIR, filename)

        if os.path.exists(dest_path):
            if not messagebox.askyesno("File Exists", "A file with this name already exists. Overwrite?"):
                return

        try:
            shutil.copy(source_path, dest_path)
            file_type = filename.split('.')[-1] if '.' in filename else 'Unknown'

            self.files = [f for f in self.files if f['filename'] != filename]

            self.files.append({
                "filename": filename,
                "type": file_type,
                "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "path": dest_path
            })
            self.update_files_ui()
        except Exception as e:
            messagebox.showerror("File Error", f"Could not copy file: {e}")

    def delete_selected_file(self):
        selected_iid = self.files_tree.focus()
        if not selected_iid:
            messagebox.showwarning("Selection Error", "Please select a file to delete.")
            return

        if messagebox.askyesno("Confirm Delete", "Are you sure you want to permanently delete this file?"):
            item_index = int(selected_iid)
            file_to_delete = self.files[item_index]
            try:
                os.remove(file_to_delete['path'])
                del self.files[item_index]
                self.update_files_ui()
            except Exception as e:
                messagebox.showerror("File Error", f"Could not delete file: {e}")

    def show_query_window(self, config_name, initial_prompt=None, initial_response=None):
        if config_name in self.open_query_windows:
            self.open_query_windows[config_name].lift()
            self.open_query_windows[config_name].focus_force()
        else:
            config_details = self.llm_configs.get(config_name)
            if config_details:
                query_window = LLMQueryWindow(self, config_name, config_details, initial_prompt, initial_response)
                self.open_query_windows[config_name] = query_window
                query_window.focus_force()

    def unregister_query_window(self, config_name):
        if config_name in self.open_query_windows:
            del self.open_query_windows[config_name]

    def start_listener(self):
        listener_thread = threading.Thread(target=self.run_keyboard_listener, daemon=True)
        listener_thread.start()

    def run_keyboard_listener(self):
        with keyboard.Listener(on_press=self.on_key_press) as listener:
            listener.join()

    def on_key_press(self, key):
        try:
            self.buffer += key.char
        except AttributeError:
            if key == keyboard.Key.space: self.buffer += " "
            elif key == keyboard.Key.backspace: self.buffer = self.buffer[:-1]
            else: self.buffer = ""
            return

        match = re.search(r'__(\d+)$', self.buffer)
        if match:
            number = int(match.group(1))
            trigger_len = len(match.group(0))
            config_names = list(self.llm_configs.keys())
            if 1 <= number <= len(config_names):
                config_to_open = config_names[number - 1]
                for _ in range(trigger_len):
                    self.keyboard_controller.press(keyboard.Key.backspace)
                    self.keyboard_controller.release(keyboard.Key.backspace)
                    time.sleep(0.01)
                self.root.after(0, self.show_query_window, config_to_open)
                self.buffer = ""
                return

        for trigger, data in self.shortcuts.items():
            if data["enabled"].get() and self.buffer.endswith(trigger):
                for _ in range(len(trigger)):
                    self.keyboard_controller.press(keyboard.Key.backspace)
                    self.keyboard_controller.release(keyboard.Key.backspace)
                    time.sleep(0.01)
                self.keyboard_controller.type(data["output"])
                self.buffer = ""
                return


if __name__ == "__main__":
    app_root = tk.Tk()
    app = DesktopUtilitiesApp(app_root)
    app_root.mainloop()
