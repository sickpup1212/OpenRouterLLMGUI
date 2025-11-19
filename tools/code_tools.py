"""Code analysis tools for searching and analyzing source code."""

import ast
import os
import re
import json
from typing import List, Dict, Union
from pathlib import Path
import logging
from tools.registry import tool_registry

logger = logging.getLogger(__name__)


@tool_registry.register(
    description="Search file contents using regular expressions to find specific patterns across codebases",
    requires_confirmation=False
)
def grep(
    pattern: str,
    path: str = ".",
    include: str = "*"
) -> str:
    """
    Tool: grep
    Search file contents using regular expressions to find specific patterns
    across codebases. Filter results by file type and retrieve paths sorted
    by modification time.

    Instructions:
    Fast content search tool that works with any codebase size.
    Searches file contents using regular expressions.
    Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.).
    Filter files by pattern with the include parameter (eg. ".js", "*.{ts,tsx}").
    Returns matching file paths sorted by modification time.
    Use this tool when you need to find files containing specific patterns.
    When you are doing an open ended search that may require multiple rounds
    of globbing and grepping, use the Agent tool instead.

    Args:
        pattern (str): The regular expression pattern to search for in
            file contents. This is required.
        path (str, optional): The directory to search in.
            Defaults to the current working directory ".".
        include (str, optional): File pattern to include in the search
            (e.g. "*.js", "*.{ts,tsx}"). Defaults to "*" (all files).

    Returns:
        str: A list of file paths that contain at least one match,
            sorted by modification time (most recently modified first).
    """
    results_with_mtime: List[tuple[float, str]] = []
    try:
        compiled_regex = re.compile(pattern)
    except re.error as e:
        print(f"Invalid regex pattern: {e}")
        return []
    search_path = Path(path)
    if not search_path.is_dir():
        print(f"Path is not a valid directory: {path}")
        return []
    try:
        files_to_search = search_path.rglob(include)
    except Exception as e:
        print(f"Error during file globbing: {e}")
        return []
    for file_path in files_to_search:
        if not file_path.is_file():
            continue
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if compiled_regex.search(content):
                mod_time = file_path.stat().st_mtime
                results_with_mtime.append((mod_time, str(file_path)))
        except (IOError, PermissionError) as e:
            print(f"Could not read file {file_path}: {e}")
        except Exception as e:
            print(f"An error occurred processing file {file_path}: {e}")
    results_with_mtime.sort(key=lambda x: x[0], reverse=True)
    final_paths = json.dumps([path_str for mod_time, path_str in results_with_mtime])
    return final_paths


class ContextVisitor(ast.NodeVisitor):
    """
    A node visitor to traverse the AST and build a map of line numbers
    to their structural context (e.g., "in class 'MyClass' -> in function 'my_func'").

    Requires Python 3.8+ for 'end_lineno' attributes on all nodes.
    """
    def __init__(self):
        self.line_context_map: Dict[int, str] = {}
        self.context_stack: List[str] = []

    def _visit_node_with_context(self, node, context_name: str):
        """
        Helper method to visit a node, record its context for all lines
        it spans, and visit its children.
        """
        start_line = getattr(node, 'lineno', -1)
        end_line = getattr(node, 'end_lineno', -1)
        if start_line == -1 or end_line == -1:
            self.generic_visit(node)
            return
        self.context_stack.append(context_name)
        current_context_str = " -> ".join(reversed(self.context_stack))
        for line_num in range(start_line, end_line + 1):
            self.line_context_map[line_num] = f"in {current_context_str}"
        self.generic_visit(node)
        self.context_stack.pop()
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_node_with_context(node, f"function '{node.name}'")
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_node_with_context(node, f"async function '{node.name}'")
    def visit_ClassDef(self, node: ast.ClassDef):
        self._visit_node_with_context(node, f"class '{node.name}'")


@tool_registry.register(
    description="Search and analyze source code using AST context to reveal structural relationships",
    requires_confirmation=False
)
def grep_ast(
    path: str,
    pattern: str,
    ignore_case: bool = False,
    line_number: bool = False
) -> str:
    """
    Tool: grep_ast
    Search and analyze source code using AST context to reveal structural
    relationships, such as functions or classes containing matching
    patterns. Ideal for understanding code organization and exploring
    unfamiliar codebases.

    Instructions:
    Search through source code files and see matching lines with useful AST
    (Abstract Syntax Tree) context. This tool helps you understand code
    structure by showing how matched lines fit into functions, classes, and
    other code blocks.

    Unlike traditional search tools like search_content that only show
    matching lines, grep_ast leverages the AST to reveal the structural
    context around matches, making it easier to understand the code
    organization.

    When to use this tool:
    - When you need to understand where a pattern appears within larger code structures.
    - When searching for function or class definitions that match a pattern.
    - When you want to see not just the matching line but its surrounding context in the code.
    - When exploring unfamiliar codebases and need structural context.
    - When examining how a specific pattern is used across different parts of the codebase.

    This tool is superior to regular grep/search_content when you need to
    understand code structure, not just find text matches.

    Example usage:
    grep_ast(pattern="function_name", path="/path/to/file.py", ignore_case=False, line_number=True)

    Args:
        path (str): The path to search in (file or directory). This is required.
        pattern (str): The regex pattern to search for in source code files.
            This is required.
        ignore_case (bool, optional): Whether to ignore case when matching.
            Defaults to False.
        line_number (bool, optional): Whether to display line numbers with
            the matches. Defaults to False.

    Returns:
        str: A stringified list of match objects. Each object is a dictionary
            containing the file path, the matching line, the AST context
            (e.g., "in function 'my_func'"), and optionally the line number.
            Example:
            [
                {
                    "file_path": "/path/to/file.py",
                    "line_number": 42,
                    "matching_line": "    def function_name(self):",
                    "ast_context": "in class 'MyClass'"
                }
            ]
    """
    results: List[Dict[str, Union[str, int]]] = []
    regex_flags = re.IGNORECASE if ignore_case else 0
    try:
        compiled_regex = re.compile(pattern, flags=regex_flags)
    except re.error as e:
        print(f"Invalid regex pattern: {e}")
        return []
    files_to_search: List[str] = []
    if os.path.isfile(path):
        if path.endswith(".py"):
            files_to_search.append(path)
    elif os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(".py"):
                    files_to_search.append(os.path.join(root, file))
    else:
        print(f"Path is not a valid file or directory: {path}")
        return []
    for file_path in files_to_search:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError) as e:
            print(f"Could not read file {file_path}: {e}")
            continue
        line_context_map: Dict[int, str] = {}
        try:
            tree = ast.parse(content, filename=file_path)
            visitor = ContextVisitor()
            visitor.visit(tree)
            line_context_map = visitor.line_context_map
        except (SyntaxError, ValueError) as e:
            print(f"Could not parse AST for {file_path}: {e}")
        except RecursionError as e:
            print(f"Could not parse AST for {file_path} (too complex/deep): {e}")
        lines = content.splitlines()
        for i, line_text in enumerate(lines):
            current_line_num = i + 1
            if compiled_regex.search(line_text):
                context = line_context_map.get(current_line_num, "global scope")
                match_data: Dict[str, Union[str, int]] = {
                    "file_path": file_path,
                    "matching_line": line_text,  # <--- FIXED
                    "ast_context": context
                }
                if line_number:
                    match_data["line_number"] = current_line_num
                results.append(match_data)
    return json.dumps(results)
