"""Tools package for file operations, code analysis, web scraping, and utilities."""

# Import registry first
from tools.registry import tool_registry

# Import all tools (this triggers the @register decorators)
from tools.batch_executor import BatchExecutor, BatchOperation, BatchResult, create_batch_function
from tools.file_tools import READ, WRITE, READ_WITH_LINES, multiedit
from tools.code_tools import grep, grep_ast, ContextVisitor
from tools.web_tools import scrape_site, scrape_site_for_links
from tools.todo_tools import ManageTodo
from tools.other_tools import THINK, linux_shell

__all__ = [
    # Registry
    'tool_registry',
    # Batch execution
    'BatchExecutor',
    'BatchOperation',
    'BatchResult',
    'create_batch_function',
    # File tools
    'READ',
    'WRITE',
    'READ_WITH_LINES',
    'multiedit',
    # Code tools
    'grep',
    'grep_ast',
    'ContextVisitor',
    # Web tools
    'scrape_site',
    'scrape_site_for_links',
    # Todo tools
    'ManageTodo',
    # Other tools
    'THINK',
    'linux_shell'
]
