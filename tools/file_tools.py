"""File manipulation tools for reading, writing, and editing files."""

import os
import logging
import difflib
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_community.tools.file_management.read import ReadFileTool
from tools.registry import tool_registry
from typing import Optional

logger = logging.getLogger(__name__)

class PrettyStr(str):
    def __repr__(self):
        return self

@tool_registry.register(
    description="Read the contents of a file from the filesystem",
    requires_confirmation=False
)
def READ(file_path):
    """
    Description:
        Read the contents of a file from the filesystem.
    Args:
        file_path (str): The absolute or relative path to the file to be read.
    Returns:
        str: The contents of the file as a string.
    Raises:
        FileNotFoundError: If the specified file does not exist.
        PermissionError: If the user doesn't have read permissions for the file.
    """
    read_file_tool = ReadFileTool()
    result = read_file_tool.run({"file_path": file_path})
    return result


@tool_registry.register(
    description="Write text and save to a file or overwrite if an existing filename is provided",
    requires_confirmation=True
)
def WRITE(file_path, content, diff_callback=None):
    """
    Description:
        Write text and save to a file or overwrite if an existing filename is provided.
    Args:
        file_path(str): The absolute or relative path to the file to be written to.
        content(str): The text that you want to be written to the file at location provided in file_path.
        diff_callback (callable): Optional callback for GUI diff display.
    Returns:
        str: A message indicating the operation was successful.
    """
    # Check if we should show diff
    if diff_callback:
        if os.path.exists(file_path):
            # Show diff for existing file
            try:
                original_content = READ(file_path)
                approved = diff_callback(original_content, content, os.path.basename(file_path))
                if not approved:
                    return "Write cancelled by user."
            except Exception as e:
                logger.warning(f"Could not show diff for WRITE: {e}")
        else:
            # Show "new file" diff (empty original)
            try:
                approved = diff_callback("", content, f"NEW: {os.path.basename(file_path)}")
                if not approved:
                    return "Write cancelled by user."
            except Exception as e:
                logger.warning(f"Could not show diff for new file: {e}")

    write_tool = WriteFileTool()
    result = write_tool.run({"file_path": file_path, "text": content})
    return result


@tool_registry.register(
    description="Returns a file's contents with line numbers added to each line of text",
    requires_confirmation=False
)
def READ_WITH_LINES(file_path: str, line_start: Optional[int] = None, num_of_lines: Optional[int] = None) -> str:
    """
    Description:
        Returns a file's contents with line numbers added to each line of text.
        Can optionally specify a starting line and a number of lines to return.
    Args:
        file_path (str): The absolute or relative path to the file to be read with lines.
        line_start (int, optional): The 1-based line number to start reading from.
                                    Lines before this are excluded.
        num_of_lines (int, optional): The number of lines to return *after* line_start.
    Returns:
        str: The contents of the file with lines as a string, formatted as a code block.
    Raises:
        FileNotFoundError: If the specified file does not exist.
        PermissionError: If the user doesn't have read permissions for the file.
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        fileContent = READ(file_path)
        lines = fileContent.splitlines()
        
        start_index = 0
        end_index = None

        if line_start is not None:
            line_start = int(line_start)
            if line_start < 1:
                line_start = 1
            start_index = line_start - 1
        
        if num_of_lines is not None:
            num_of_lines = int(num_of_lines)
            if num_of_lines < 0:
                num_of_lines = 0
            end_index = start_index + num_of_lines
        
        sliced_lines = lines[start_index:end_index]
        
        rList = []
        for i, line in enumerate(sliced_lines, start=start_index):
            line_number = i + 1
            rList.append(f"{line_number}| {line}\n")
        
        # --- UPDATED SECTION ---
        # Get file extension for syntax highlighting
        file_ext = os.path.splitext(file_path)[1].lstrip('.')
        if not file_ext:
            file_ext = 'text' # default to plain text

        if not rList:
            if line_start and line_start > len(lines):
                return f"```\nFile only has {len(lines)} lines. Line {line_start} is out of bounds.\n```"
            return f"```\n--- No lines selected for: {file_path} [L{line_start}-{line_start+(num_of_lines or 0)}] ---\n```"
        
        # Join the list of lines
        output_content = ''.join(rList)

        # Return wrapped in a markdown code block
        return f"```{file_ext}\n{output_content}```"
        # --- END UPDATED SECTION ---
        
    except Exception as error:
        # Also wrap errors in a code block for consistency
        return f"```\nError: {str(error)}\n```"

@tool_registry.register(
    description="Edits a file based on a list of structured edit operations (insert, replace, delete)",
    requires_confirmation=True
)
def multiedit(file_path, edits, preview=False, diff_callback=None):
    """
    Description:
        Edits a file based on a list of structured edit operations.
    Args:
        file_path (str): The path to the file to edit.
        edits (list): A list of dictionaries, each specifying an edit.
                      Each dict must have 'operation', 'line_number', and 'content' (for insert/replace).
        preview (bool): If True, shows a diff and asks for confirmation before writing.
        diff_callback (callable): Optional callback function for GUI diff display.
                                 Should accept (original, updated, filename) and return bool.
    Returns:
        str: A message indicating success or failure.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    # Validate the edits structure first
    for i, edit in enumerate(edits):
        if not all(k in edit for k in ['operation', 'line_number']):
            return f"Error: Edit #{i+1} is missing 'operation' or 'line_number'."
        if edit['operation'] in ['insert', 'replace'] and 'content' not in edit:
            return f"Error: Edit #{i+1} ('{edit['operation']}') is missing 'content'."

    original_content = READ(file_path)
    lines = original_content.splitlines()

    # CRITICAL STEP: Sort edits by line number in reverse order.
    edits.sort(key=lambda x: x['line_number'], reverse=True)

    try:
        for edit in edits:
            op = edit['operation']
            line_index = edit['line_number'] - 1

            if line_index < 0 or line_index >= len(lines) and op != 'insert':
                return f"Error: Line number {edit['line_number']} is out of bounds for the file."

            if op == 'replace':
                lines[line_index] = edit['content']
            elif op == 'insert':
                if line_index > len(lines):
                    line_index = len(lines)
                lines.insert(line_index, edit['content'])
            elif op == 'delete':
                del lines[line_index]
            else:
                return f"Error: Unknown operation '{op}'."
    except (IndexError, KeyError) as e:
        return f"An error occurred while processing edits: {e}"

    updated_content = "\n".join(lines)

    # --- Preview Integration ---
    if preview or diff_callback:
        if diff_callback:
            # GUI callback provided - use it
            approved = diff_callback(original_content, updated_content, os.path.basename(file_path))
            if not approved:
                return "Edit cancelled by user."
        else:
            # CLI fallback
            diff = difflib.unified_diff(
                original_content.splitlines(keepends=True),
                updated_content.splitlines(keepends=True),
                fromfile='original',
                tofile='modified',
            )
            print("--- PROPOSED CHANGES ---")
            print("".join(diff))
            confirm = input("Apply these changes? (y/n): ").lower()
            if confirm != 'y':
                return "Edit cancelled by user."

    WRITE(file_path, updated_content)
    return f"Successfully applied {len(edits)} edits to {file_path}."
