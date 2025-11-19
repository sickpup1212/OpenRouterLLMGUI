"""Tool registry system for auto-discovery of tools."""

from typing import Callable, Dict, Any, Optional
import inspect


class ToolRegistry:
    """Centralized registry for tool functions with auto-discovery."""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        requires_confirmation: bool = False
    ):
        """
        Decorator to register a tool function.

        Args:
            name: Tool name (defaults to function name)
            description: Tool description (defaults to docstring)
            requires_confirmation: Whether tool requires GUI confirmation

        Example:
            @tool_registry.register(name="my_tool", requires_confirmation=True)
            def my_tool(arg1, arg2):
                return "result"
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_description = description or (func.__doc__ or "").strip()

            self._tools[tool_name] = func
            self._metadata[tool_name] = {
                "description": tool_description,
                "requires_confirmation": requires_confirmation,
                "signature": inspect.signature(func)
            }

            return func
        return decorator

    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> Dict[str, Callable]:
        """Get all registered tools."""
        return self._tools.copy()

    def get_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a tool."""
        return self._metadata.get(name)

    def list_tools(self) -> list:
        """List all registered tool names."""
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools


# Global registry instance
tool_registry = ToolRegistry()
