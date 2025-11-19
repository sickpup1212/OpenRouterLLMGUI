"""Batch execution system for running multiple tool operations sequentially."""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Callable
import logging

logger = logging.getLogger(__name__)


@dataclass
class BatchOperation:
    """Single operation in a batch."""
    tool: str
    args: Dict[str, Any]
    store_result_as: Optional[str] = None  # Variable name to store result


@dataclass
class BatchResult:
    """Result of a single batch operation."""
    tool: str
    args: Dict[str, Any]
    success: bool
    result: Any
    error: Optional[str] = None
    stored_as: Optional[str] = None


class BatchExecutor:
    """
    Execute multiple tool calls in sequence with context passing.
    """
    def __init__(self, tool_mapping: Dict[str, Callable], stop_on_error: bool = True):
        """
        Initialize batch executor.

        Args:
            tool_mapping: Dictionary mapping tool names to functions
            stop_on_error: If True, stop execution on first error
        """
        self.tool_mapping = tool_mapping
        self.stop_on_error = stop_on_error
        self.context: Dict[str, Any] = {}  # Stores results from operations

    def execute(self, operations: List[Dict[str, Any]]) -> List[BatchResult]:
        """
        Execute a batch of operations.
        """
        results = []
        self.context = {}  # Reset context for each batch

        for i, op in enumerate(operations):
            tool_name = "unknown" # Default in case of key error
            try:
                # Parse operation
                tool_name = op.get('tool')
                args = op.get('args', {})
                store_as = op.get('store_result_as')

                if not tool_name:
                    results.append(BatchResult(
                        tool="unknown",
                        args={},
                        success=False,
                        result=None,
                        error="Missing 'tool' field in operation"
                    ))
                    if self.stop_on_error:
                        break
                    continue

                # Validate tool exists
                if tool_name not in self.tool_mapping:
                    results.append(BatchResult(
                        tool=tool_name,
                        args=args,
                        success=False,
                        result=None,
                        error=f"Unknown tool: {tool_name}"
                    ))
                    if self.stop_on_error:
                        break
                    continue

                # Resolve variable references in args
                resolved_args = self._resolve_variables(args)

                # Execute tool
                logger.info(f"Batch[{i+1}/{len(operations)}]: {tool_name}({resolved_args})")
                tool_func = self.tool_mapping[tool_name]
                result = tool_func(**resolved_args)

                # Store result if requested
                if store_as:
                    self.context[store_as] = result
                    logger.info(f"Stored result as '{store_as}'")

                results.append(BatchResult(
                    tool=tool_name,
                    args=resolved_args,
                    success=True,
                    result=result,
                    stored_as=store_as
                ))

            except Exception as e:
                error_msg = f"Error executing {tool_name}: {str(e)}"
                logger.error(error_msg, exc_info=True) # Log full traceback

                results.append(BatchResult(
                    tool=tool_name,
                    args=op.get('args', {}), # Use original args for error report
                    success=False,
                    result=None,
                    error=error_msg
                ))

                if self.stop_on_error:
                    logger.warning("Stopping batch execution due to error")
                    break

        return results

    def _resolve_variables(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve variable references in arguments.
        Variables are referenced as "$variable_name"
        """
        resolved = {}

        for key, value in args.items():
            if isinstance(value, str) and value.startswith('$'):
                var_name = value[1:]  # Remove $
                if var_name in self.context:
                    resolved[key] = self.context[var_name]
                    logger.debug(f"Resolved ${var_name} -> {self.context[var_name]}")
                else:
                    logger.warning(f"Variable ${var_name} not found in context")
                    resolved[key] = value  # Keep original if not found
            else:
                resolved[key] = value

        return resolved

    def format_results(self, results: List[BatchResult]) -> str:
        """Format results as a readable string."""
        output = ["=== BATCH EXECUTION RESULTS ===\n"]

        for i, result in enumerate(results, 1):
            output.append(f"[{i}] {result.tool}")

            if result.success:
                output.append(f"    ✓ Success")
                if result.stored_as:
                    output.append(f"    Stored as: ${result.stored_as}")
                if result.result:
                    # Truncate long results
                    result_str = str(result.result)
                    if len(result_str) > 200:
                        result_str = result_str[:200] + "..."
                    output.append(f"    Result: {result_str}")
            else:
                output.append(f"    ✗ Failed: {result.error}")

            output.append("")  # Empty line between results

        # Summary
        success_count = sum(1 for r in results if r.success)
        output.append(f"Summary: {success_count}/{len(results)} operations succeeded")

        return "\n".join(output)


def create_batch_function(tool_mapping: Dict[str, Callable]) -> Callable:
    """
    Creates a BATCH function that is bound to a specific tool_mapping.
    """
    def batch_tool_call(operations: List[Dict[str, Any]], stop_on_error: bool = True) -> str:
        """
        Execute multiple tool calls in sequence.

        Args:
            operations: List of operations to execute. Each operation is a dict with:
                - tool: Name of the tool to call
                - args: Dictionary of arguments to pass
                - store_result_as (optional): Variable name to store result
            stop_on_error: If True, stop execution on first error

        Returns:
            Formatted string with results of all operations
        """
        executor = BatchExecutor(tool_mapping, stop_on_error)
        results = executor.execute(operations)
        return executor.format_results(results)

    return batch_tool_call
