"""Main application class for Desktop Utilities."""

import tkinter as tk
from tkinter import ttk, Text, messagebox, filedialog
import threading
import time
import os
import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from pynput import keyboard
import requests
import logging

# GUI imports
from gui.llm_query_window import LLMQueryWindow
from gui.other_windows import SelectProfileWindow, SelectToolsWindow

# LLM imports
from llm import LLMClient, AgentManager, OpenRouterAPIParameters

# Tools imports
from tools import (
    tool_registry,  # Import the auto-discovery registry
    ManageTodo,
    linux_shell  # Import for wrapping with confirmation callback
)
from tools.batch_executor import create_batch_function

logger = logging.getLogger(__name__)


class DesktopUtilitiesApp:
    CONFIG_FILE = "config.json"
    FILES_DIR = "saved_files"
    AGENTS_DIR = os.getenv("AGENT_DIRECTORY", "./agents")

    def __init__(self, root):
        self.root = root
        self.root.title("Desktop Utilities")
        self.root.geometry("950x800") # Increased window size

        self.shortcuts = {}
        self.llm_configs = {}
        self.llm_profiles = {}
        self.saved_items = []
        self.files = []
        self.tools = []
        self.open_query_windows = {}
        self.openrouter_models = []
        self.models_data = []

        self.buffer = ""
        self.keyboard_controller = keyboard.Controller()

        self.todo_mgmt = ManageTodo()  # --- NEW: Initialize todo manager ---

        self.agent_directory = Path(self.AGENTS_DIR)
        self.agent_tool_schemas = {
            "READ": {
                "type": "function",
                "function": {
                    "name": "READ",
                    "description": "Read the contents of a file from the filesystem",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "The absolute or relative path to the file to be read"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            "READ_WITH_LINES": {
                "type": "function",
                "function": {
                    "name": "READ_WITH_LINES",
                    "description": "Read a file with line numbers prepended to each line. Can optionally specify a starting line and a number of lines to return.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "The path to the file to read with line numbers"
                            },
                            "line_start": {
                                "type": "integer",
                                "description": "Optional 1-based line number to start reading from. (e.g., 100)"
                            },
                            "num_of_lines": {
                                "type": "integer",
                                "description": "Optional number of lines to read *after* line_start. (e.g., 20)"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            "multiedit": {
                "type": "function",
                "function": {
                    "name": "multiedit",
                    "description": "Apply multiple line-specific edits to a file. Operations: insert, replace, delete. Line numbers start at 1.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to edit"
                            },
                            "edits": {
                                "type": "array",
                                "description": "List of edit operations to apply",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "operation": {
                                            "type": "string",
                                            "enum": ["insert", "replace", "delete"],
                                            "description": "Type of edit operation"
                                        },
                                        "line_number": {
                                            "type": "integer",
                                            "description": "Line number to edit (1-indexed)"
                                        },
                                        "content": {
                                            "type": "string",
                                            "description": "New content (required for insert/replace)"
                                        }
                                    },
                                    "required": ["operation", "line_number"]
                                }
                            },
                            "preview": {
                                "type": "boolean",
                                "description": "Show diff preview before applying",
                                "default": True
                            }
                        },
                        "required": ["file_path", "edits"]
                    }
                }
            },
            "WRITE": {
                "type": "function",
                "function": {
                    "name": "WRITE",
                    "description": "Write or overwrite a file with new content. Use for creating new files or complete rewrites.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to write"
                            },
                            "content": { # --- MODIFIED --- "text" -> "content"
                                "type": "string",
                                "description": "Complete content to write to the file"
                            }
                        },
                        "required": ["file_path", "content"] # --- MODIFIED --- "text" -> "content"
                    }
                }
            },
            "THINK": {
                "type": "function",
                "function": {
                    "name": "THINK",
                    "description": "Log a thought for complex reasoning, brainstorming, or planning. Use when you need to organize ideas, explore solutions, or make complex decisions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "thought": {
                                "type": "string",
                                "description": "The thought, reasoning, or brainstorming content. Be concise and structured.",
                            }
                        },
                        "required": ["thought"]
                    }
                }
            },
            "scrape_site": {
                "type": "function",
                "function": {
                    "name": "scrape_site",
                    "description": "scrape some data from a website of your choosing",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "a url for an online website"
                            }
                        },
                        "required": [
                            "url"
                        ]
                    }
                }
            },
            "scrape_site_for_links": {
                "type": "function",
                "function": {
                    "name": "scrape_site_for_links",
                    "description": "get a list of dictionaries that contain the link textContent and href for every a element in your url",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "a url for an online website"
                            },
                            "start": {
                                "type": "integer",
                                "description": "a starting index to limit the list of data returned ie results[start:end]"
                            },
                            "end": {
                                "type": "integer",
                                "description": "an ending index to limit the list of data returned ie results[start:end]"
                            }
                        },
                        "required": [
                            "url"
                        ]
                    }
                }
            },
            "grep_ast": {
                "type": "function",
                "function": {
                    "name": "grep_ast",
                    "description": "Search and analyze source code using AST context to reveal structural relationships, such as functions or classes containing matching patterns. Ideal for understanding code organization and exploring unfamiliar codebases.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path to search in (file or directory). This is required."
                            },
                            "pattern": {
                                "type": "string",
                                "description": "The regex pattern to search for in source code files. This is required."
                            },
                            "ignore_case": {
                                "type": "boolean",
                                "description": "Whether to ignore case when matching. Defaults to False."
                            },
                            "line_number": {
                                "type": "boolean",
                                "description": "Whether to display line numbers with the matches. Defaults to False."
                            }
                        },
                        "required": ["path", "pattern"]
                    }
                }
            },
            "grep": {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "Search file contents using regular expressions to find specific patterns across codebases. Filter results by file type and retrieve paths sorted by modification time.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "The regular expression pattern to search for in file contents. This is required."
                            },
                            "path": {
                                "type": "string",
                                "description": "The directory to search in. Defaults to the current working directory \".\"."
                            },
                            "include": {
                                "type": "string",
                                "description": "File pattern to include in the search (e.g. \"*.js\", \"*.{ts,tsx}\"). Defaults to \"*\" (all files)."
                            }
                        },
                        "required": ["pattern"]
                    }
                }
            },
            "todo_read": {
                "type": "function",
                "function": {
                    "name": "todo_read",
                    "description": "Get all the current information about your todo list instance. Returns JSON with session info, todos array, and counts by status.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            "todo_write": {
                "type": "function",
                "function": {
                    "name": "todo_write",
                    "description": "Add a new item to your todo list. Use this when you need to track a task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Description of the task that needs to be done."
                            }
                        },
                        "required": ["content"]
                    }
                }
            },
            "todo_update": {
                "type": "function",
                "function": {
                    "name": "todo_update",
                    "description": "Update the status of a todo list entry. Use the todo_id to identify which entry to update.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "todo_id": {
                                "type": "string",
                                "description": "The ID string that identifies which entry to update."
                            },
                            "new_status": {
                                "type": "string",
                                "enum": ["completed", "in_progress", "pending", "cancelled"],
                                "description": "The new status to set for this todo item."
                            }
                        },
                        "required": ["todo_id", "new_status"]
                    }
                }
            },
            "todo_get_ids": {
                "type": "function",
                "function": {
                    "name": "todo_get_ids",
                    "description": "Get a list of all current todo_ids that are not completed or cancelled. Useful for bulk operations.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            "todo_write_many": {
                "type": "function",
                "function": {
                    "name": "todo_write_many",
                    "description": "Create multiple todo entries at once by passing a list of content strings. Each string becomes a separate todo item.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content_list": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "List of strings, each will be used as 'content' to create a todo entry."
                            }
                        },
                        "required": ["content_list"]
                    }
                }
            },
            "todo_update_many": {
                "type": "function",
                "function": {
                    "name": "todo_update_many",
                    "description": "Update the status of multiple todo entries at once using a list of todo_ids.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "todo_id_list": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "List of todo_ids to update. Only active (not completed/cancelled) todos should be included."
                            },
                            "new_status": {
                                "type": "string",
                                "enum": ["completed", "in_progress", "pending", "cancelled"],
                                "description": "The new status to set for all todos in the list."
                            }
                        },
                        "required": ["todo_id_list", "new_status"]
                    }
                }
            }
        }
        self.active_agent_manager = None
        self.active_llm_client = None

        # --- NEW --- Auto-Discovered Tool Registry
        # Start with all auto-registered tools from decorators
        self.tool_registry = tool_registry.get_all_tools()

        # Add todo management tools (instance methods)
        self.tool_registry.update({
            "todo_read": self.todo_mgmt.todoRead,
            "todo_write": self.todo_mgmt.todoWrite,
            "todo_update": self.todo_mgmt.todoUpdate,
            "todo_get_ids": self.todo_mgmt.todoGetOpenIds,
            "todo_write_many": self.todo_mgmt.todoWriteMany,
            "todo_update_many": self.todo_mgmt.todoUpdateMany
        })

        # Create a confirmation callback for GUI dialogs
        def shell_confirmation_callback(command: str) -> bool:
            """GUI callback for linux_shell command confirmation."""
            return messagebox.askyesno(
                "Confirm Shell Command",
                f"Execute this command?\n\n{command}\n\nOnly allow if you trust this command.",
                icon='warning'
            )

        # Wrap linux_shell with the confirmation callback
        def linux_shell_with_gui(command: str) -> str:
            """Wrapper for linux_shell that includes GUI confirmation."""
            return linux_shell(command, confirmation_callback=shell_confirmation_callback)

        # Replace linux_shell in registry with the GUI-enabled version
        self.tool_registry["linux_shell"] = linux_shell_with_gui

        self.setup_directories()
        self.load_data()
        self.create_widgets()
        self.start_listener()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_directories(self):
        if not os.path.exists(self.FILES_DIR):
            os.makedirs(self.FILES_DIR)
        if not os.path.exists(self.agent_directory): # --- NEW ---
            os.makedirs(self.agent_directory)

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
                    self.tools = data.get("tools", [])
                    # --- MODIFIED ---
                    # Ensure call_agent and get_agent_names are in self.tools
                    # so they are selectable in the UI.
                    tool_names = {t.get('function', {}).get('name') for t in self.tools}
                    call_agent_schema = self.agent_tool_schemas.get("call_agent")
                    if call_agent_schema and "call_agent" not in tool_names:
                        self.tools.append(call_agent_schema)
                    get_agents_schema = self.agent_tool_schemas.get("get_agent_names")
                    if get_agents_schema and "get_agent_names" not in tool_names:
                        self.tools.append(get_agents_schema)
                    # --- END MODIFIED ---
            except json.JSONDecodeError:
                messagebox.showerror("Config Error", "Failed to load config.json. It might be corrupted.")
            finally:
                # Ensure core tools are in self.tools so they are selectable in the UI.
                tool_names = {t.get('function', {}).get('name') for t in self.tools}
                core_schemas = {
                    "call_agent": self.agent_tool_schemas.get("call_agent"),
                    "get_agent_names": self.agent_tool_schemas.get("get_agent_names"),
                    "BATCH": self.agent_tool_schemas.get("BATCH"),
                    # --- NEW: Add todo tools to core schemas ---
                    "todo_read": self.agent_tool_schemas.get("todo_read"),
                    "todo_write": self.agent_tool_schemas.get("todo_write"),
                    "todo_update": self.agent_tool_schemas.get("todo_update"),
                    "todo_get_ids": self.agent_tool_schemas.get("todo_get_ids"),
                    "todo_write_many": self.agent_tool_schemas.get("todo_write_many"),
                    "todo_update_many": self.agent_tool_schemas.get("todo_update_many")
                }
                for name, schema in core_schemas.items():
                    if schema and name not in tool_names:
                        self.tools.append(schema)

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
            "files": self.files,
            "tools": self.tools
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
        tools_tab = ttk.Frame(notebook)
        agents_tab = ttk.Frame(notebook) # --- NEW ---
        saved_items_tab = ttk.Frame(notebook)
        files_tab = ttk.Frame(notebook)

        notebook.add(shortcut_tab, text='Text Shortcuts')
        notebook.add(llm_tab, text='LLM Models')
        notebook.add(profiles_tab, text='LLM Profiles')
        notebook.add(tools_tab, text='Tools')
        notebook.add(agents_tab, text='Agents') # --- NEW ---
        notebook.add(saved_items_tab, text='Saved Items')
        notebook.add(files_tab, text='Files')

        self.create_shortcut_tab(shortcut_tab)
        self.create_llm_tab(llm_tab)
        self.create_config_profiles_tab(profiles_tab)
        self.create_tools_tab(tools_tab)
        self.create_agents_tab(agents_tab) # --- NEW ---
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
            ("Verbosity", "verbosity", ["low", "medium", "high"], "combobox"),
        ]

        self.profile_entries = {}
        row_counter = 2
        for label, key, default, widget_type in fields:
            ttk.Label(editor_frame, text=f"{label}:").grid(row=row_counter, column=0, padx=5, pady=2, sticky="w")

            # Special handling for the 'tools' parameter
            if key == "tools":
                tools_frame = ttk.Frame(editor_frame)
                widget = Text(tools_frame, height=5, width=30)
                widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                select_button = ttk.Button(tools_frame, text="Select...", command=lambda w=widget: self.open_select_tools_window(w))
                select_button.pack(side=tk.LEFT, padx=(5, 0), anchor='n')
                tools_frame.grid(row=row_counter, column=1, columnspan=2, padx=5, pady=2, sticky="ew")
                editor_frame.columnconfigure(1, weight=1)
            else:
                if widget_type == "text":
                    widget = Text(editor_frame, height=3, width=30)
                    # FIX: Initially set to NORMAL state so it's editable
                    widget.config(state=tk.NORMAL)
                elif widget_type == "entry":
                    widget = ttk.Entry(editor_frame)
                elif widget_type == "spinbox_float":
                    widget = ttk.Spinbox(editor_frame, from_=0.0, to=2.0, increment=0.1, format="%.1f", width=10)
                    widget.set(default)
                elif widget_type == "spinbox_int":
                    widget = ttk.Spinbox(editor_frame, from_=0, to=8192, width=10)
                    widget.set(default)
                elif widget_type == "combobox":
                    widget = ttk.Combobox(editor_frame, values=default, state="readonly")
                    widget.set(default[1])

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
            self.profile_entries[key] = var
            row_counter += 1

        # DON'T disable fields initially - let user start typing
        # They'll be controlled when a model is selected

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

    def open_select_tools_window(self, tools_text_widget):
        SelectToolsWindow(self, tools_text_widget)

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
        """Toggle profile fields based on model support."""
        for key, widget in self.profile_entries.items():
            if enable:
                if supported_params is None or key in supported_params:
                    if isinstance(widget, tk.BooleanVar):
                        pass
                    elif isinstance(widget, Text):
                        widget.config(state=tk.NORMAL)
                    else:
                        widget.config(state=tk.NORMAL)
                else:
                    if isinstance(widget, Text):
                        widget.config(state=tk.DISABLED)
                    elif not isinstance(widget, tk.BooleanVar):
                        widget.config(state=tk.DISABLED)
                    else:
                        if isinstance(widget, Text):
                            widget.config(state=tk.DISABLED)
                        elif not isinstance(widget, tk.BooleanVar):
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

            if not value and not isinstance(value, bool): # Skip empty values, but not boolean False
                continue

            # Process and store the value
            if key == 'tools' and isinstance(value, str):
                try:
                    settings[key] = json.loads(value)
                except json.JSONDecodeError:
                    messagebox.showerror("JSON Error", "Invalid JSON format in the 'Tools' field.", parent=self.root)
                    return
            # --- PASTE THIS NEW BLOCK HERE ---
            elif key == 'response_format' and isinstance(value, str):
                if value == 'json_object':
                    # Automatically convert the simple string to the object Pydantic expects
                    settings[key] = {"type": "json_object"}
                elif value.startswith('{'):
                    # User typed the full JSON object, let's try to parse it
                    try:
                        settings[key] = json.loads(value)
                    except json.JSONDecodeError:
                        messagebox.showerror("JSON Error", "Invalid JSON in 'Response Format'.", parent=self.root)
                        return
                # If it's empty, it will be skipped by the `if not value` check above
            # --- END OF NEW BLOCK ---
            elif isinstance(widget, ttk.Spinbox):
                try:
                    settings[key] = float(value) if "." in str(widget.cget('format')) else int(value)
                except ValueError:
                    settings[key] = value # Fallback to string if conversion fails
            else:
                settings[key] = value

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

    def create_tools_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(1, weight=1)

        # Editor frame for creating/editing tools
        editor_frame = ttk.LabelFrame(main_frame, text="Create/Edit Tool", padding="10")
        editor_frame.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        editor_frame.columnconfigure(1, weight=1)

        ttk.Label(editor_frame, text="Tool Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.tool_name_entry = ttk.Entry(editor_frame)
        self.tool_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(editor_frame, text="Description:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.tool_description_entry = ttk.Entry(editor_frame)
        self.tool_description_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(editor_frame, text="Parameters (JSON Schema):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.tool_params_text = Text(editor_frame, height=10, width=40)
        self.tool_params_text.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        save_button = ttk.Button(editor_frame, text="Save Tool", command=self.save_tool)
        save_button.grid(row=3, column=1, pady=10, sticky="e")

        # List frame for displaying saved tools
        list_frame = ttk.LabelFrame(main_frame, text="Saved Tools", padding="10")
        list_frame.grid(row=0, column=1, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.tools_tree = ttk.Treeview(list_frame, columns=('name', 'description'), show='headings')
        self.tools_tree.heading('name', text='Tool Name')
        self.tools_tree.heading('description', text='Description')
        self.tools_tree.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.tools_tree.bind('<<TreeviewSelect>>', self.load_tool_for_editing)

        delete_button = ttk.Button(list_frame, text="Delete Selected", command=self.delete_tool)
        delete_button.pack()

        self.update_tools_ui()

    def update_tools_ui(self):
        self.tools_tree.delete(*self.tools_tree.get_children())
        for i, tool in enumerate(self.tools):
            func = tool.get('function', {})
            self.tools_tree.insert('', tk.END, iid=i, values=(func.get('name', ''), func.get('description', '')))

    # --- FIXED --- This method now correctly parses and saves the tool's parameter JSON
    def save_tool(self):
        name = self.tool_name_entry.get().strip()
        description = self.tool_description_entry.get().strip()
        params_str = self.tool_params_text.get("1.0", tk.END).strip()

        if not name:
            messagebox.showwarning("Input Error", "Tool Name is required.", parent=self.root)
            return

        try:
            # The parameters field should contain a valid JSON Schema object.
            params = json.loads(params_str) if params_str else {"type": "object", "properties": {}}
        except json.JSONDecodeError:
            messagebox.showerror("JSON Error", "Invalid JSON in Parameters field. Please provide a valid JSON Schema object.", parent=self.root)
            return

        # Find tool by function name
        tool_to_update = None
        for t in self.tools:
            if t.get('function', {}).get('name') == name:
                tool_to_update = t
                break

        if tool_to_update:
            if messagebox.askyesno("Confirm Overwrite", f"A tool named '{name}' already exists. Do you want to overwrite it?"):
                tool_to_update['function']['description'] = description
                tool_to_update['function']['parameters'] = params
            else:
                return  # User cancelled overwrite
        else:
            # Add new tool
            new_tool = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": params
                }
            }
            self.tools.append(new_tool)

        self.update_tools_ui()
        # Clear fields
        self.tool_name_entry.delete(0, tk.END)
        self.tool_description_entry.delete(0, tk.END)
        self.tool_params_text.delete("1.0", tk.END)
        messagebox.showinfo("Success", f"Tool '{name}' saved successfully.", parent=self.root)


    def delete_tool(self):
        selected_item = self.tools_tree.focus()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Please select a tool to delete.", parent=self.root)
            return

        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete the selected tool?"):
            item_index = int(self.tools_tree.item(selected_item, "text")) # This is incorrect, need to use iid
            item_index = int(selected_item)
            del self.tools[item_index]
            self.update_tools_ui()

    def load_tool_for_editing(self, event=None):
        selected_item = self.tools_tree.focus()
        if not selected_item:
            return

        item_index = int(selected_item)
        tool = self.tools[item_index]
        function_def = tool.get('function', {})

        self.tool_name_entry.delete(0, tk.END)
        self.tool_name_entry.insert(0, function_def.get('name', ''))

        self.tool_description_entry.delete(0, tk.END)
        self.tool_description_entry.insert(0, function_def.get('description', ''))

        self.tool_params_text.delete("1.0", tk.END)
        params_json = json.dumps(function_def.get('parameters', {}), indent=4)
        self.tool_params_text.insert("1.0", params_json)

    def load_profile_for_editing(self, event=None):
        """Load a selected profile into the editor for editing."""
        selected_item = self.profiles_tree.focus()
        if not selected_item:
            return

        profile_name = self.profiles_tree.item(selected_item)['values'][0]
        profile_data = self.llm_profiles.get(profile_name, {})

        model_name = profile_data.get("model")
        if model_name and model_name in self.openrouter_models:
            self.profile_model_combo.set(model_name)
            self.on_profile_model_select()
        else:
            self.profile_model_combo.set("Select a model to see parameters")
            # Don't disable fields when loading - keep them editable
            self.toggle_profile_fields(True)

        self.profile_name_entry.delete(0, tk.END)
        self.profile_name_entry.insert(0, profile_name)

        for key, widget in self.profile_entries.items():
            value = profile_data.get(key, "")

            if isinstance(widget, tk.BooleanVar):
                widget.set(bool(value))
            elif isinstance(widget, Text):
                # FIX: Ensure Text widget is NORMAL before modifying
                widget.config(state=tk.NORMAL)
                widget.delete("1.0", tk.END)
                if key == 'tools' and isinstance(value, list):
                    widget.insert("1.0", json.dumps(value, indent=4))
                else:
                    widget.insert("1.0", str(value))
                # FIX: Keep it NORMAL after inserting (don't disable)
                # widget.config(state=tk.NORMAL)  # Already set above, stays NORMAL
            elif isinstance(widget, ttk.Entry):
                widget.delete(0, tk.END)
                widget.insert(0, str(value))
            elif isinstance(widget, ttk.Combobox):
                widget.set(str(value))
            elif isinstance(widget, ttk.Spinbox):
                widget.set(str(value) if value else "0")

    def create_agents_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(3, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # 1. Config Selection
        config_frame = ttk.Frame(main_frame)
        config_frame.grid(row=0, column=0, sticky="ew", pady=5)
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Select Model Config:").grid(row=0, column=0, padx=(0, 5), sticky="w")
        self.agent_model_config_combo = ttk.Combobox(config_frame, state="readonly", values=list(self.llm_configs.keys()))
        self.agent_model_config_combo.grid(row=0, column=1, sticky="ew")
        self.agent_model_config_combo.bind("<<ComboboxSelected>>", self.initialize_agent_manager)

        # 2. Agent Selection
        agent_frame = ttk.Frame(main_frame)
        agent_frame.grid(row=1, column=0, sticky="ew", pady=5)
        agent_frame.columnconfigure(1, weight=1)

        ttk.Label(agent_frame, text="Select Agent:").grid(row=0, column=0, padx=(0, 5), sticky="w")
        self.agent_select_combo = ttk.Combobox(agent_frame, state="disabled")
        self.agent_select_combo.grid(row=0, column=1, sticky="ew")
        self.agent_select_combo.bind("<<ComboboxSelected>>", self.load_agent_example)


        # 3. Prompt
        prompt_frame = ttk.LabelFrame(main_frame, text="Prompt", padding="10")
        prompt_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        prompt_frame.rowconfigure(0, weight=1)
        prompt_frame.columnconfigure(0, weight=1)

        self.agent_prompt_text = Text(prompt_frame, height=5, font=("Arial", 10))
        self.agent_prompt_text.pack(fill=tk.BOTH, expand=True)

        # 4. Result
        result_frame = ttk.LabelFrame(main_frame, text="Result", padding="10")
        result_frame.grid(row=3, column=0, sticky="nsew", pady=5)
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        self.agent_result_text = Text(result_frame, state="disabled", wrap=tk.WORD, font=("Arial", 10))
        result_scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.agent_result_text.yview)
        self.agent_result_text['yscrollcommand'] = result_scrollbar.set
        self.agent_result_text.grid(row=0, column=0, sticky="nsew")
        result_scrollbar.grid(row=0, column=1, sticky="ns")

        # 5. Run Button
        self.agent_run_button = ttk.Button(main_frame, text="Run Agent", command=self.run_agent_threaded, state="disabled")
        self.agent_run_button.grid(row=4, column=0, sticky="e", pady=5)

    def initialize_agent_manager(self, event=None):
        config_name = self.agent_model_config_combo.get()
        if not config_name:
            return

        config = self.llm_configs.get(config_name)
        if not config:
            messagebox.showerror("Error", f"Config '{config_name}' not found.")
            return

        api_key = config.get("api_key")
        model = config.get("model")

        if not api_key or not model:
            messagebox.showerror("Error", "Selected config is missing API key or model.")
            return

        try:
            # 1. Create the client
            self.active_llm_client = LLMClient(api_key, model)

            # 2. Create the tool registry for this agent manager
            # Start with the app's base tools
            active_tool_registry = self.tool_registry.copy()

            # 3. Create the agent manager
            self.active_agent_manager = AgentManager(
                self.agent_directory,
                self.active_llm_client,
                active_tool_registry,      # Pass the registry
                self.agent_tool_schemas,   # Pass the schemas
                max_iterations=15
            )

            # 4. Add the manager's own tools to its registry (as per user's code)
            active_tool_registry["call_agent"] = self.active_agent_manager.call_agent
            active_tool_registry["get_agent_names"] = self.active_agent_manager.get_agent_names

            # 5. Re-set the manager's tool_mapping to the now-complete registry
            self.active_agent_manager.tool_mapping = active_tool_registry
            # Create a BATCH function bound to this manager's complete tool map
            batch_func = create_batch_function(self.active_agent_manager.tool_mapping)
            active_tool_registry["BATCH"] = batch_func
            self.active_agent_manager.tool_mapping["BATCH"] = batch_func # Redundant but safe
            # --- END NEW ---

            # 6. Load agent names into combo
            agent_names_json = self.active_agent_manager.get_agent_names()
            agent_names = json.loads(agent_names_json)

            # 6. Load agent names into combo
            #agent_names = self.active_agent_manager.get_agent_names()
            if not agent_names:
                messagebox.showwarning("No Agents Found", f"No agent '.md' files found in {self.agent_directory.resolve()}.")
                self.agent_select_combo['values'] = []
                self.agent_select_combo.set("No agents found")
                self.agent_select_combo.config(state="disabled")
                self.agent_run_button.config(state="disabled")
                return

            self.agent_select_combo['values'] = agent_names
            self.agent_select_combo.config(state="readonly")
            self.agent_select_combo.set("Select an agent")
            self.agent_run_button.config(state="normal")

        except Exception as e:
            messagebox.showerror("Agent Init Error", f"Failed to initialize agent manager: {e}")
            self.agent_select_combo.config(state="disabled")
            self.agent_run_button.config(state="disabled")
            logger.error("Agent Init Error", exc_info=True)

    def load_agent_example(self, event=None):
        """Load the agent's example prompt into the prompt box."""
        if not self.active_agent_manager:
            return

        agent_name = self.agent_select_combo.get()
        if not agent_name or agent_name == "Select an agent":
            return

        try:
            agent_config = self.active_agent_manager.load_agent(agent_name)
            if agent_config.example:
                self.agent_prompt_text.delete("1.0", tk.END)
                self.agent_prompt_text.insert("1.0", agent_config.example)
        except Exception as e:
            logger.warning(f"Could not load agent example: {e}")


    def run_agent_threaded(self):
        agent_name = self.agent_select_combo.get()
        prompt = self.agent_prompt_text.get("1.0", tk.END).strip()

        if not self.active_agent_manager:
            messagebox.showwarning("Error", "Agent manager is not initialized. Select a model config.", parent=self.root)
            return
        if not agent_name or agent_name == "Select an agent" or agent_name == "No agents found":
            messagebox.showwarning("Error", "Please select an agent.", parent=self.root)
            return
        if not prompt:
            messagebox.showwarning("Error", "Please enter a prompt.", parent=self.root)
            return

        self.agent_run_button.config(state="disabled")
        self.agent_model_config_combo.config(state="disabled")
        self.agent_select_combo.config(state="disabled")
        self.agent_result_text.config(state="normal")
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert(tk.END, f"Running agent '{agent_name}'...\n\nThis may take several minutes and involve multiple steps.")
        self.agent_result_text.config(state="disabled")

        thread = threading.Thread(target=self.run_agent_task, args=(agent_name, prompt), daemon=True)
        thread.start()

    def run_agent_task(self, agent_name, prompt):
        try:
            result = self.active_agent_manager.call_agent(agent_name, prompt)
            self.root.after(0, self.update_agent_result, result)
        except Exception as e:
            error_msg = f"Agent execution failed: {e}"
            logger.error(error_msg, exc_info=True)
            self.root.after(0, self.update_agent_result, error_msg)
        finally:
            self.root.after(0, lambda: self.agent_run_button.config(state="normal"))
            self.root.after(0, lambda: self.agent_model_config_combo.config(state="readonly"))
            self.root.after(0, lambda: self.agent_select_combo.config(state="readonly"))

    def update_agent_result(self, result):
        self.agent_result_text.config(state="normal")
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert(tk.END, result)
        self.agent_result_text.config(state="disabled")

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
            # NEW
            prompt_str = str(item.get('prompt', ''))
            response_str = str(item.get('response', ''))
            content_preview = (prompt_str + response_str)[:75].replace('\n', ' ') + "..."
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
        self.files_tree_view = ttk.Treeview(tree_frame, columns=columns, show='headings') # Renamed to avoid conflict
        self.files_tree_view.heading('filename', text='Filename')
        self.files_tree_view.heading('type', text='Type')
        self.files_tree_view.heading('date_added', text='Date Added')
        self.files_tree_view.column('filename', width=300, anchor=tk.W)
        self.files_tree_view.column('type', width=100, anchor=tk.W)
        self.files_tree_view.column('date_added', width=150, anchor=tk.W)
        self.files_tree_view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.files_tree_view.yview)
        self.files_tree_view.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        action_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="Add File", command=self.add_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="Delete Selected File", command=self.delete_selected_file).pack(side=tk.LEFT)
        self.update_files_ui()

    def update_files_ui(self):
        self.files_tree_view.delete(*self.files_tree_view.get_children())
        for i, item in enumerate(self.files):
            values = (item['filename'], item['type'], item['date_added'])
            self.files_tree_view.insert('', tk.END, iid=i, values=values)

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
        selected_iid = self.files_tree_view.focus()
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
            # Some keys don't have a char attribute, check first
            if hasattr(key, 'char') and key.char is not None:
                self.buffer += key.char
            else:
                # Handle special keys
                if key == keyboard.Key.space:
                    self.buffer += " "
                elif key == keyboard.Key.backspace:
                    self.buffer = self.buffer[:-1] if self.buffer else ""
                else:
                    # Other special keys clear the buffer
                    self.buffer = ""
                return
        except AttributeError:
            # Fallback for any unexpected key handling issues
            if key == keyboard.Key.space:
                self.buffer += " "
            elif key == keyboard.Key.backspace:
                self.buffer = self.buffer[:-1] if self.buffer else ""
            else:
                self.buffer = ""
            return

        # Check for LLM trigger pattern
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
