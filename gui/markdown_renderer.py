"""Markdown rendering for tkinter Text widgets."""

import tkinter as tk
import re


class MarkdownRenderer:
    """Renders Markdown text in a tkinter Text widget with styling."""

    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.setup_tags()

    def setup_tags(self):
        """Configure text tags for different Markdown elements."""
        try:
            from tkinter import font as tkfont
            default_font = tkfont.Font(font=self.text_widget['font'])
            family = default_font.actual()['family']
            size = default_font.actual()['size']
        except:
            # Fallback if font detection fails
            family = "Arial"
            size = 11

        # Headers
        self.text_widget.tag_configure("h1", font=(family, size + 8, "bold"), spacing3=10)
        self.text_widget.tag_configure("h2", font=(family, size + 6, "bold"), spacing3=8)
        self.text_widget.tag_configure("h3", font=(family, size + 4, "bold"), spacing3=6)
        self.text_widget.tag_configure("h4", font=(family, size + 2, "bold"), spacing3=4)
        self.text_widget.tag_configure("h5", font=(family, size + 1, "bold"), spacing3=3)
        self.text_widget.tag_configure("h6", font=(family, size, "bold"), spacing3=2)

        # Text formatting
        self.text_widget.tag_configure("bold", font=(family, size, "bold"))
        self.text_widget.tag_configure("italic", font=(family, size, "italic"))
        self.text_widget.tag_configure("bold_italic", font=(family, size, "bold italic"))
        self.text_widget.tag_configure("code_inline", font=("Courier", size), background="#f0f0f0")

        # Code blocks
        self.text_widget.tag_configure("code_block", font=("Courier", size), background="#f5f5f5",
                                      lmargin1=20, lmargin2=20, spacing1=5, spacing3=5)

        # Lists
        self.text_widget.tag_configure("list_item", lmargin1=20, lmargin2=40)

        # Blockquotes
        self.text_widget.tag_configure("blockquote", lmargin1=20, lmargin2=20,
                                      foreground="#666666", font=(family, size, "italic"))

        # Links
        self.text_widget.tag_configure("link", foreground="blue", underline=True)

        # Horizontal rule
        self.text_widget.tag_configure("hr", foreground="#cccccc")

    def render(self, markdown_text):
        """Parse and render Markdown text in the Text widget."""
        if not markdown_text:
            return

        try:
            lines = markdown_text.split('\n')
            i = 0
            in_code_block = False
            code_block_lines = []

            while i < len(lines):
                line = lines[i]

                # Code blocks (```)
                if line.strip().startswith('```'):
                    if not in_code_block:
                        in_code_block = True
                        code_block_lines = []
                    else:
                        # End of code block
                        self.insert_code_block('\n'.join(code_block_lines))
                        in_code_block = False
                        code_block_lines = []
                    i += 1
                    continue

                if in_code_block:
                    code_block_lines.append(line)
                    i += 1
                    continue

                # Headers
                header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
                if header_match:
                    level = len(header_match.group(1))
                    text = header_match.group(2)
                    self.insert_header(level, text)
                    i += 1
                    continue

                # Horizontal rule
                if re.match(r'^(\*\*\*|---|___)$', line.strip()):
                    self.insert_hr()
                    i += 1
                    continue

                # Unordered list
                list_match = re.match(r'^[\*\-\+]\s+(.+)$', line)
                if list_match:
                    self.insert_list_item(list_match.group(1))
                    i += 1
                    continue

                # Ordered list
                ordered_match = re.match(r'^\d+\.\s+(.+)$', line)
                if ordered_match:
                    self.insert_list_item(ordered_match.group(1))
                    i += 1
                    continue

                # Blockquote
                if line.startswith('>'):
                    quote_text = line[1:].strip()
                    self.insert_blockquote(quote_text)
                    i += 1
                    continue

                # Regular paragraph with inline formatting
                if line.strip():
                    self.insert_paragraph(line)
                else:
                    self.text_widget.insert(tk.END, '\n')

                i += 1
        except Exception as e:
            # If markdown rendering fails, just insert as plain text
            print(f"Markdown rendering error: {e}")
            self.text_widget.insert(tk.END, markdown_text)

    def insert_header(self, level, text):
        """Insert a header with appropriate styling."""
        tag = f"h{level}"
        # Process inline formatting in header
        self.insert_with_inline_formatting(text, base_tag=tag)
        self.text_widget.insert(tk.END, '\n')

    def insert_code_block(self, code):
        """Insert a code block."""
        self.text_widget.insert(tk.END, code + '\n', "code_block")

    def insert_list_item(self, text):
        """Insert a list item."""
        self.text_widget.insert(tk.END, "• ", "list_item")
        self.insert_with_inline_formatting(text, base_tag="list_item")
        self.text_widget.insert(tk.END, '\n')

    def insert_blockquote(self, text):
        """Insert a blockquote."""
        self.insert_with_inline_formatting(text, base_tag="blockquote")
        self.text_widget.insert(tk.END, '\n')

    def insert_paragraph(self, text):
        """Insert a regular paragraph with inline formatting."""
        self.insert_with_inline_formatting(text)
        self.text_widget.insert(tk.END, '\n')

    def insert_hr(self):
        """Insert a horizontal rule."""
        self.text_widget.insert(tk.END, '─' * 50 + '\n', "hr")

    def insert_with_inline_formatting(self, text, base_tag=None):
        """Parse and insert text with inline Markdown formatting."""
        # Pattern for inline code, bold, italic, and links
        pattern = r'(`[^`]+`|\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*|___[^_]+___|__[^_]+__|_[^_]+_|\[([^\]]+)\]\(([^\)]+)\))'

        last_end = 0
        matches = list(re.finditer(pattern, text))

        if not matches:
            # No formatting found, insert as plain text
            tags = (base_tag,) if base_tag else ()
            self.text_widget.insert(tk.END, text, tags)
            return

        for match in matches:
            # Insert text before match
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                tags = (base_tag,) if base_tag else ()
                self.text_widget.insert(tk.END, plain_text, tags)

            matched_text = match.group(0)

            # Inline code
            if matched_text.startswith('`') and matched_text.endswith('`'):
                code_text = matched_text[1:-1]
                tags = ("code_inline", base_tag) if base_tag else ("code_inline",)
                self.text_widget.insert(tk.END, code_text, tags)

            # Bold + Italic
            elif (matched_text.startswith('***') and matched_text.endswith('***')) or \
                 (matched_text.startswith('___') and matched_text.endswith('___')):
                content = matched_text[3:-3]
                tags = ("bold_italic", base_tag) if base_tag else ("bold_italic",)
                self.text_widget.insert(tk.END, content, tags)

            # Bold
            elif (matched_text.startswith('**') and matched_text.endswith('**')) or \
                 (matched_text.startswith('__') and matched_text.endswith('__')):
                content = matched_text[2:-2]
                tags = ("bold", base_tag) if base_tag else ("bold",)
                self.text_widget.insert(tk.END, content, tags)

            # Italic
            elif (matched_text.startswith('*') and matched_text.endswith('*')) or \
                 (matched_text.startswith('_') and matched_text.endswith('_')):
                content = matched_text[1:-1]
                tags = ("italic", base_tag) if base_tag else ("italic",)
                self.text_widget.insert(tk.END, content, tags)

            # Links
            elif matched_text.startswith('['):
                link_text = match.group(2)
                link_url = match.group(3)
                tags = ("link", base_tag) if base_tag else ("link",)
                self.text_widget.insert(tk.END, link_text, tags)

            last_end = match.end()

        # Insert remaining text
        if last_end < len(text):
            plain_text = text[last_end:]
            tags = (base_tag,) if base_tag else ()
            self.text_widget.insert(tk.END, plain_text, tags)
