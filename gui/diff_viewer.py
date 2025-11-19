"""Diff viewer window for displaying file changes."""

import tkinter as tk
from tkinter import ttk, Text, Toplevel
import difflib


class DiffViewerWindow(Toplevel):
    """Window to display file diffs with HTML rendering and approve/reject buttons."""
    def __init__(self, parent, original_content, updated_content, filename="file"):
        super().__init__(parent)
        self.title(f"Review Changes - {filename}")
        self.transient(parent)
        self.geometry("900x700")
        self.result = None  # Will be True (accept) or False (reject)

        self.create_widgets(original_content, updated_content)

        # Make this window modal
        self.grab_set()
        self.wait_window()

    def create_widgets(self, original_content, updated_content):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # HTML diff display
        diff_frame = ttk.LabelFrame(main_frame, text="Proposed Changes", padding="10")
        diff_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        diff_frame.rowconfigure(0, weight=1)
        diff_frame.columnconfigure(0, weight=1)

        try:
            from tkinterweb import HtmlFrame
            self.diff_display = HtmlFrame(diff_frame, messages_enabled=False)
            self.diff_display.grid(row=0, column=0, sticky="nsew")

            # Generate and display HTML diff
            html_diff = self.generate_html_diff(original_content, updated_content)
            self.diff_display.load_html(html_diff)
        except ImportError:
            # Fallback to Text widget
            self.diff_display = Text(diff_frame, wrap=tk.NONE, font=("Courier", 10))
            self.diff_display.grid(row=0, column=0, sticky="nsew")

            scrollbar_y = ttk.Scrollbar(diff_frame, orient=tk.VERTICAL, command=self.diff_display.yview)
            scrollbar_y.grid(row=0, column=1, sticky="ns")
            scrollbar_x = ttk.Scrollbar(diff_frame, orient=tk.HORIZONTAL, command=self.diff_display.xview)
            scrollbar_x.grid(row=1, column=0, sticky="ew")
            self.diff_display.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

            # Generate text diff
            diff = difflib.unified_diff(
                original_content.splitlines(keepends=True),
                updated_content.splitlines(keepends=True),
                fromfile='original',
                tofile='modified',
            )
            self.diff_display.insert("1.0", "".join(diff))
            self.diff_display.config(state=tk.DISABLED)

        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, sticky="ew")

        ttk.Label(button_frame, text="Apply these changes?", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Button(button_frame, text="✓ Accept (Yes)", command=self.accept_changes, style="Accent.TButton").pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="✗ Reject (No)", command=self.reject_changes).pack(side=tk.RIGHT, padx=5)

    def generate_html_diff(self, original, updated):
        """Generate an HTML representation of the diff."""
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile='original',
            tofile='modified',
            lineterm=''
        )

        html_parts = ["""
        <html>
        <head>
        <style>
            body {
                font-family: 'Courier New', monospace;
                font-size: 12px;
                padding: 10px;
                background-color: #f8f9fa;
                margin: 0;
            }
            .diff-line {
                padding: 2px 5px;
                margin: 0;
                white-space: pre;
                line-height: 1.4;
            }
            .diff-header {
                color: #6c757d;
                font-weight: bold;
                background-color: #e9ecef;
                padding: 4px 5px;
                margin: 8px 0 2px 0;
            }
            .diff-removed {
                background-color: #ffeef0;
                color: #d73a49;
            }
            .diff-added {
                background-color: #e6ffed;
                color: #22863a;
            }
            .diff-context {
                color: #24292e;
            }
            .diff-info {
                background-color: #d4edff;
                color: #0366d6;
                font-weight: bold;
            }
        </style>
        </head>
        <body>
        """]

        for line in diff:
            line = line.rstrip('\n')
            escaped_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            if line.startswith('---') or line.startswith('+++'):
                html_parts.append(f'<div class="diff-line diff-header">{escaped_line}</div>')
            elif line.startswith('@@'):
                html_parts.append(f'<div class="diff-line diff-info">{escaped_line}</div>')
            elif line.startswith('-'):
                html_parts.append(f'<div class="diff-line diff-removed">{escaped_line}</div>')
            elif line.startswith('+'):
                html_parts.append(f'<div class="diff-line diff-added">{escaped_line}</div>')
            else:
                html_parts.append(f'<div class="diff-line diff-context">{escaped_line}</div>')

        html_parts.append('</body></html>')
        return ''.join(html_parts)

    def accept_changes(self):
        self.result = True
        self.destroy()

    def reject_changes(self):
        self.result = False
        self.destroy()
