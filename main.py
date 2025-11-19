"""Main entry point for the Desktop Utilities application."""

import tkinter as tk
from app import DesktopUtilitiesApp

if __name__ == "__main__":
    app_root = tk.Tk()
    app = DesktopUtilitiesApp(app_root)
    app_root.mainloop()
