import json
import os
from tkinter import messagebox

def load_config(config_file):
    """Loads the configuration from a JSON file."""
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            messagebox.showerror("Config Error", f"Failed to load {config_file}. It might be corrupted.")
            return {}
    return {}

def save_config(config_file, data):
    """Saves the configuration to a JSON file."""
    with open(config_file, 'w') as f:
        json.dump(data, f, indent=4)