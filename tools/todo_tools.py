"""Todo management tools for task tracking."""

import json
from todo_implementation import TodoManager


class ManageTodo:
    """Wrapper class for TodoManager to provide simplified tool interface."""
    def __init__(self):
        self.tm = TodoManager()
        
    def todoGetOpenIds(self) -> str:
        """Get list of all open (not completed/cancelled) todo IDs."""
        return json.dumps(self.tm.get_open_todo_ids())

    def todoRead(self):
        """Get all current todo list information."""
        read_data = self.tm.todo_read(session_id=self.tm.SESSION_ID)
        return read_data  # Return as string, already JSON formatted

    def todoWrite(self, content: str) -> str:
        """Add a new todo item."""
        write_data = self.tm.todo_write(action='add', content=content)
        return write_data

    def todoUpdate(self, todo_id: str, new_status: str) -> str:
        """Update the status of a specific todo item."""
        update_data = self.tm.todo_write(action='update', todo_id=todo_id, status=new_status)
        return update_data

    def todoGetOpenIds(self) -> str:
        """Get list of all open (not completed/cancelled) todo IDs."""
        return json.dumps(self.tm.get_open_todo_ids())

    def todoWriteMany(self, content_list: list) -> str:
        """Create multiple todo items from a list of content strings."""
        result = self.tm.add_multiple(content_list)
        # --- MODIFICATION ---
        # Return the full todo_read() JSON string so the UI can format it
        return self.tm.todo_read(self.tm.SESSION_ID)

    def todoUpdateMany(self, todo_id_list: list, new_status: str) -> str:
        """Update status of multiple todo items."""
        result = self.tm.update_multiple_status(todo_id_list, new_status)
        # --- MODIFICATION ---
        # Return the full todo_read() JSON string so the UI can format it
        return self.tm.todo_read(self.tm.SESSION_ID)
