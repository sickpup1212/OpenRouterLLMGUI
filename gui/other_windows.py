"""Supporting dialog windows for the application."""

import tkinter as tk
from tkinter import ttk, Text, Toplevel, messagebox
import json


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
            pass  # Ignore errors in parsing existing content

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
