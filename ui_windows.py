import tkinter as tk
from tkinter import ttk, messagebox, Toplevel, Text, filedialog
import threading
import requests
import base64
import os
import json
from models import OpenRouterAPIParameters
from api import call_openrouter_api


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

        text_response, role = call_openrouter_api(
            api_key,
            model_name,
            self.history,
            self.advanced_settings
        )

        if role == "error":
            self.append_to_chat_display(text_response, "error")
        else:
            self.history.append({"role": role, "content": text_response})
            self.update_chat_display()

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


class SelectToolsWindow(Toplevel):
    """Window to select tools for an LLM profile."""
    def __init__(self, parent_app, tools_text_widget):
        super().__init__(parent_app.root)
        self.title("Select Tools")
        self.transient(parent_app.root)
        self.geometry("400x500")
        self.app = parent_app
        self.tools_text_widget = tools_text_widget
        self.tool_vars = []

        self.create_widgets()
        self.load_current_tools()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Select tools to include in the profile:").pack(anchor="w", pady=(0, 10))

        # Scrollable frame for checkboxes
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        for tool in self.app.tools:
            var = tk.BooleanVar()
            tool_name = tool.get('function', {}).get('name', 'Unnamed Tool')
            chk = ttk.Checkbutton(self.scrollable_frame, text=tool_name, variable=var)
            chk.pack(anchor="w", padx=10, pady=5)
            self.tool_vars.append((var, tool))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Apply", command=self.apply_selection).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def load_current_tools(self):
        try:
            current_tools_str = self.tools_text_widget.get("1.0", tk.END).strip()
            if not current_tools_str:
                return
            current_tools_data = json.loads(current_tools_str)
            if not isinstance(current_tools_data, list):
                return
            current_tool_names = {t.get('function', {}).get('name') for t in current_tools_data}

            for var, tool in self.tool_vars:
                tool_name = tool.get('function', {}).get('name')
                if tool_name in current_tool_names:
                    var.set(True)
        except (json.JSONDecodeError, AttributeError):
            pass # Ignore errors in parsing existing content

    def apply_selection(self):
        selected_tools = []
        for var, tool in self.tool_vars:
            if var.get():
                selected_tools.append(tool)

        self.tools_text_widget.delete("1.0", tk.END)
        if selected_tools:
            # Pretty-print JSON into the Text widget
            self.tools_text_widget.insert("1.0", json.dumps(selected_tools, indent=4))

        self.destroy()