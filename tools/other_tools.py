"""Miscellaneous utility tools."""

import subprocess
import shlex
from datetime import datetime
from typing import Optional, Callable
from tools.registry import tool_registry


@tool_registry.register(
    description="Log a thought for complex reasoning, brainstorming, or planning",
    requires_confirmation=False
)
def THINK(thought: str) -> str:
    """
    Log a thought for complex reasoning, brainstorming, or planning.
    Use when you need to organize ideas, explore solutions, or make
    complex decisions. The thought is logged and confirmed.
    """
    # Optionally log to file
    with open("./thoughts/thoughts.log", "a") as f:
        f.write(f"{datetime.now()}: {thought}\n")
    confirmation = f"Thought logged: {thought}"
    return confirmation


def _parse_command_safely(command: str) -> list:
    """
    Parse a command string into a list for safe execution.

    Args:
        command: The command string to parse

    Returns:
        List of command parts for subprocess.run

    Raises:
        ValueError: If command contains dangerous patterns
    """
    # Remove dangerous patterns
    dangerous_patterns = [';', '&&', '||', '|', '>', '<', '`', '$()']
    for pattern in dangerous_patterns:
        if pattern in command:
            raise ValueError(f"Command contains dangerous pattern: '{pattern}'")

    # Use shlex to safely split the command
    try:
        return shlex.split(command)
    except ValueError as e:
        raise ValueError(f"Invalid command syntax: {e}")


@tool_registry.register(
    description="Execute shell commands in a controlled environment with safety checks",
    requires_confirmation=True
)
def linux_shell(command: str, confirmation_callback: Optional[Callable[[str], bool]] = None) -> str:
    """
    Execute shell commands in a controlled environment with safety checks.

    Args:
        command: The shell command to be executed.
        confirmation_callback: Optional GUI callback function that returns True/False
                             for user confirmation. If None, command is rejected.

    Returns:
        str: Command output if successful, error message if failed, user response
             message if execution was declined, or error details if an exception occurred.

    Raises:
        ValueError: If the command is not in the allowed commands list or contains
                   dangerous patterns.

    Security Notes:
        - Only whitelisted commands are allowed
        - Uses shell=False to prevent injection attacks
        - Blocks command chaining (;, &&, ||, |)
        - Blocks redirection (>, <)
        - Blocks command substitution (``, $())
        - Requires explicit user confirmation via GUI
    """
    # Whitelist of allowed commands
    allowed_commands = [
        "ls", "pwd", "echo", "cat", "whoami", "grep", "find",
        "touch", "tail", "head", "mkdir", "stat", "tree",
        "npm", "python3", "python", "node", "git",
        "mv", "cp", "rm", "chmod", "chown"
    ]

    # Check if command starts with an allowed command
    command_parts = command.strip().split()
    if not command_parts:
        return "Error: Empty command"

    base_command = command_parts[0]
    if base_command not in allowed_commands:
        return f"Error: Command not allowed: '{base_command}'. Allowed commands: {', '.join(allowed_commands)}"

    # Parse command safely
    try:
        parsed_command = _parse_command_safely(command)
    except ValueError as e:
        return f"Error: {e}"

    # Request confirmation via callback
    if confirmation_callback is None:
        return "Error: No confirmation callback provided. Command execution requires user approval."

    try:
        approved = confirmation_callback(command)
        if not approved:
            return "Command execution declined by user"

        # Execute with shell=False for security
        result = subprocess.run(
            parsed_command,
            shell=False,
            text=True,
            capture_output=True,
            timeout=30  # Add timeout to prevent hanging
        )

        if result.returncode == 0:
            return result.stdout if result.stdout else "Command completed successfully (no output)"
        else:
            return f"Command failed with exit code {result.returncode}:\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {e}"
