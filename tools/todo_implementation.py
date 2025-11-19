import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, TypedDict

class TodoItem(TypedDict):
    id: str
    session_id: str
    content: str
    status: Literal['pending', 'in_progress', 'completed', 'cancelled']
    priority: Literal['low', 'medium', 'high']
    created_at: str
    updated_at: str

TodoSession = Dict[str, List[TodoItem]]

class TodoManager:
    """
    Manages todo lists for different sessions, equivalent to the
    todoRead and todoWrite logic in the TypeScript app.
    """

    def __init__(self, default_session_id: str = "main"):
        self.todo_sessions: TodoSession = {}
        self.SESSION_ID = default_session_id
        self._log_message("system", "TodoManager initialized.")
        self.open_todos = []

    def _log_message(self, level: str, message: str):
        """Helper to simulate the 'addMessage' function."""
        print(f"[{level.upper()}] {message}")

    def _generate_id(self) -> str:
        """Generates a unique todo ID."""
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        random_part = uuid.uuid4().hex[:9]
        return f"todo_{timestamp}_{random_part}"

    def _now_iso(self) -> str:
        """Returns the current time as a UTC ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()

    def get_open_todo_ids(self) -> list[str]:
        open_todo_ids = []
        for i in json.loads(self.todo_read(self.SESSION_ID))['todos']:
            if i['status'] != 'completed':
                open_todo_ids.append(i['id'])
        return open_todo_ids

    def add_multiple(self, list_of_content) -> list[str]:
        for i in list_of_content:
            self.todo_write(action='add', content=i)
        todos = self.get_open_todo_ids()
        for i in todos:
            self.open_todos.append(i)
        print(f"OPEN TODOS: {self.open_todos}")
        return 'multiple todos added successfully'

    def update_multiple_status(self, list_of_todo_ids: list[str], new_status: str) -> list[str]:
        for i in list_of_todo_ids:
            if new_status == 'completed':
                self.todo_write(action='update', todo_id=i, status=new_status)
                self.open_todos.remove(i)
            else:
                self.todo_write(action='update', todo_id=i, status=new_status)
        check_opens = self.get_open_todo_ids()
        if check_opens != self.open_todos:
            self.open_todos = []
            for i in check_opens:
                self.open_todos.append(i)
        print(f"OPEN TODOS: {self.open_todos}")
        return 'multiple todos changed status succesfully'

    def todo_read(self, session_id: Optional[str] = None) -> str:
        """
        Read the current todo list for the session.
        Returns all todos with their status, priority, and content as a JSON string.

        Equivalent to the 'todoRead' function.
        """
        if session_id is None:
            session_id = self.SESSION_ID
        todos = self.todo_sessions.get(session_id, [])
        if not todos:
            self._log_message("system", "📋 Todo list is empty")
            return json.dumps({"session_id": session_id, "todos": [], "total": 0})
        summary = {
            "session_id": session_id,
            "total": len(todos),
            "pending": sum(1 for t in todos if t['status'] == 'pending'),
            "in_progress": sum(1 for t in todos if t['status'] == 'in_progress'),
            "completed": sum(1 for t in todos if t['status'] == 'completed'),
            "cancelled": sum(1 for t in todos if t['status'] == 'cancelled'),
            "todos": todos
        }
        self._log_message(
            "system",
            f"📋 Todo list: {summary['pending']} pending, "
            f"{summary['in_progress']} in progress, "
            f"{summary['completed']} completed"
        )
        return json.dumps(summary, indent=2)

    def todo_write(
        self,
        action: Literal['add', 'update', 'delete', 'clear'],
        session_id: Optional[str] = None,
        todo_id: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[Literal['pending', 'in_progress', 'completed', 'cancelled']] = None,
        priority: Optional[Literal['low', 'medium', 'high']] = None
    ) -> str:
        """
        Create and manage todos for the session.
        Actions: add, update, delete, clear.

        Equivalent to the 'todoWrite' function.
        """
        if session_id is None:
            session_id = self.SESSION_ID
        session_todos = self.todo_sessions.get(session_id, [])
        updated_todos = list(session_todos)
        message = ""
        if action == 'add':
            if not content:
                self._log_message("error", "Cannot add todo: content is required.")
            else:
                new_todo: TodoItem = {
                    "id": self._generate_id(),
                    "session_id": session_id,
                    "content": content,
                    "status": status or 'pending',
                    "priority": priority or 'medium',
                    "created_at": self._now_iso(),
                    "updated_at": self._now_iso()
                }
                updated_todos.append(new_todo)
                message = f'✅ Added todo: "{content[:50]}{"..." if len(content) > 50 else ""}"'
        elif action == 'update':
            if not todo_id:
                self._log_message("error", "Cannot update todo: todo_id is required.")
            else:
                todo_index = next((i for i, t in enumerate(updated_todos) if t['id'] == todo_id), -1)
                if todo_index == -1:
                    self._log_message("error", f"Todo not found: {todo_id}")
                else:
                    existing_todo = updated_todos[todo_index]
                    existing_todo['content'] = content or existing_todo['content']
                    existing_todo['status'] = status or existing_todo['status']
                    existing_todo['priority'] = priority or existing_todo['priority']
                    existing_todo['updated_at'] = self._now_iso()
                    status_emoji = '✅' if existing_todo['status'] == 'completed' else \
                                   '🔄' if existing_todo['status'] == 'in_progress' else \
                                   '❌' if existing_todo['status'] == 'cancelled' else '📝'
                    message = (
                        f"{status_emoji} Updated todo: "
                        f'"{existing_todo["content"][:50]}" → {existing_todo["status"]}'
                    )
        elif action == 'delete':
            if not todo_id:
                self._log_message("error", "Cannot delete todo: todo_id is required.")
            else:
                delete_index = next((i for i, t in enumerate(updated_todos) if t['id'] == todo_id), -1)
                if delete_index == -1:
                    self._log_message("error", f"Todo not found: {todo_id}")
                else:
                    deleted_todo = updated_todos.pop(delete_index)
                    message = f'🗑️ Deleted todo: "{deleted_todo["content"][:50]}"'
        elif action == 'clear':
            updated_todos = []
            message = f"🗑️ Cleared all todos for session: {session_id}"
        if message:
            self.todo_sessions[session_id] = updated_todos
            self._log_message("system", message)
        return self.todo_read(session_id)
        
"""        
def TO_DO_WRITE(
    action: Literal['add', 'update', 'delete', 'clear'],
    instance: TodoManager,
    session_id: Optional[str] = None,
    todo_id: Optional[str] = None,
    content: Optional[str] = None,
    status: Optional[Literal['pending', 'in_progress', 'completed', 'cancelled']] = None,
    priority: Optional[Literal['low', 'medium', 'high']] = None,
    ):
	#tm = TodoManager()
	do_this = instance.todo_write(action, session_id, todo_id, content, status, priority)
	do_this_json = json.loads(do_this)
	do_this_session_id = do_this_json['session_id']
	print(f"SESSION_ID: {do_this_session_id}")
	do_this_todo_id = do_this_json['todos'][0]['id']
	print(f"TODO_ID: {do_this_todo_id}")
	eyedees = json.dumps({"session_id": do_this_session_id, "todo_id": do_this_todo_id})
	returnarray = [eyedees, instance]
	return returnarray
		
def TO_DO_READ(instance: TodoManager, session_id: Optional[str] = None) -> str:
	#tm = TodoManager()
	do_that = instance.todo_read(session_id)
	do_it = json.loads(do_that)
	do_it_session_id = do_it['session_id']
	do_it_todo_id = do_it['todos'][0]['id']
	ids = json.dumps({"session_id": do_it_session_id, "todo_id": do_it_todo_id})
	payload = [ids, instance]
	return payload
	
def TODO_CHANGE_STATUS(instance: TodoManager, sessionid: str, todoid: str, new_status: str):
	response = instance.todo_write(action="update", session_id=sessionid, todo_id=todoid, status=new_status, priority="medium")
	do_it = json.loads(response)
	completed = do_it['completed']
	pending = do_it['pending']
	total = do_it['total']
	do_it_session_id = do_it['session_id']
	do_it_todo_id = do_it['todos'][0]['id']
	ids = json.dumps({"session_id": do_it_session_id, "todo_id": do_it_todo_id, "total": total, "pending": pending, "completed": completed})
	payload = [ids, instance]
	return payload
	
	
def TO_DO_QUICK_LIST(todo_list: List[str], instance: TodoManager):	
	todo_one = TO_DO_WRITE(action='add', instance=instance, content=todo_list[0])
	todomgmt = todo_one[1]
	ids_dict = json.loads(todo_one[0])
	tsession_id = ids_dict['session_id']
	ttodo_id = ids_dict['todo_id']
	for i in todo_list[1:]:
		todomgmt.todo_write(
		    action='add',
		    session_id=tsession_id,
		    todo_id=ttodo_id,
		    content=i,
		    status="pending",
		    priority="low"
		)
	rd = TO_DO_READ(todomgmt, tsession_id)
	return rd
	
TO_DO_WRITE_SCHEMA = {
  "name": "TO_DO_WRITE",
  "description": "Create and manage todos for complex multi-step tasks. Use to add, update, delete, or clear todos. Mark tasks 'in_progress' when starting, 'completed' when done.",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "description": "Action to perform: add (new todo), update (modify existing), delete (remove one), clear (remove all).",
        "enum": [
          "add",
          "update",
          "delete",
          "clear"
        ]
      },
      "session_id": {
        "type": "string",
        "description": "Session identifier. Defaults to the main session if not provided."
      },
      "todo_id": {
        "type": "string",
        "description": "ID of the todo to update or delete. Required for 'update' and 'delete' actions."
      },
      "content": {
        "type": "string",
        "description": "Todo content/description. Required for 'add', optional for 'update'."
      },
      "status": {
        "type": "string",
        "description": "Todo status. Default is 'pending' for new todos.",
        "enum": [
          "pending",
          "in_progress",
          "completed",
          "cancelled"
        ]
      },
      "priority": {
        "type": "string",
        "description": "Todo priority. Default is 'medium'.",
        "enum": [
          "low",
          "medium",
          "high"
        ]
      }
    },
    "required": [
      "action"
    ]
  }
}

TO_DO_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "TO_DO_READ",
        "description": "Read the current todo list for the session. Use proactively to track tasks, check status, and plan next steps.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier. Defaults to the main session if not provided."
                }
            },
            "required": []
        }
    }
 }
 
TO_DO_QUICK_LIST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "TO_DO_QUICK_LIST",
        "description": "Create multiple TO_DO_WRITE calls by just passing a list of the content for each one",
        "parameters": {
            "type": "object",
            "properties": {
                "todo_list": {
                    "type": "array",
                    "description": "a list of todo_write content. each entry in the list will add a TO_DO using the entry as content.",
                    "items": {
                        "type": "string"
					}
                }
            },
            "required": ["todo_list"]
        }
    }
 }
 
TO_DO_WRITE_BROKEN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "TO_DO_WRITE",
        "description": "Create and manage todos for complex multi-step tasks. Use to add, update, delete, or clear todos. Mark tasks 'in_progress' when starting, 'completed' when done.",
        "parameters": {
		    "type": "object",
			"properties": {
			    "action": {
				    "type": "string",
					"description": "Action to perform: add (new todo), update (modify existing), delete (remove one), clear (remove all).",
					"enum": [
					    "add",
                        "update",
                        "delete",
						"clear"
					]
				},
				"session_id": {
				    "type": "string",
				    "description": "Session identifier. Defaults to the main session if not provided."
				},				
                "todo_id": {
                    "type": "string",
					"description": "ID of the todo to update or delete. Required for 'update' and 'delete' actions."
				},
				"content": {
			        "type": "string",
			        "description": "Todo content/description. Required for 'add', optional for 'update'."
			    },
			    "status": {
				    "type": "string",
				    "description": "Todo status. Default is 'pending' for new todos.",
					"enum": [
					    "pending",
					    "in_progress",
					    "completed",
					    "cancelled"
					]
			    },
			    "priority": {
				    "type": "string",
				    "description": "Todo priority. Default is 'medium'.",
				    "enum": [
				        "low",
				         "medium",
				         "high"
				    ]
			    },
			},
			"required": [
			    "action"
			]
		}
	}
}

def to_do_tool(**kwargs):
    k_args = {}    
    if 'action' in kwargs:
        k_args['action'] = kwargs['action']
        print(f"ACTION: {k_args['action']}")
    if 'content' in kwargs:
        k_args['content'] = kwargs['content']
        print(f"CONTENT: {k_args['content']}")
    if 'status' in kwargs:
        k_args['status'] = kwargs['status']
        print(f"STATUS: {k_args['status']}")
    if 'session_id' in kwargs:
        k_args['session_id'] = kwargs['session_id']
        print(f"SESSION_ID: {k_args['session_id']}")
    if 'todo_id' in kwargs:
        k_args['todo_id'] = kwargs['todo_id']
        print(f"TODO_ID: {k_args['todo_id']}")
    if 'priority' in kwargs:
        k_args['priority'] = kwargs['priority']
        print(f"PRIORITY: {k_args['priority']}")
    if 'task' in kwargs:
        k_args['task'] = kwargs['task']
        print(f"TASK: {k_args['task']}")
    if 'todoids' in kwargs:
        k_args['todoids'] = kwargs['todoids']
        print(f"TO DO IDS: {k_args['todoids']}")
    if k_args['task'] == 'write':
        del k_args['task']
        if type(k_args['todoids']) == list:
            temp = k_args['todoids']
            del k_args['todoids']
            response = tm.todo_write(**k_args)
            response = json.loads(response)
            temp.append(response['todos'][0]['id'])
            return temp
        else:
            res = tm.todo_write(**k_args)
            res = json.loads(res)
            td = res['todos'][-1]['id']
            print(f'SESSION_ID: {res['session_id']}')
            return td
    if k_args['task'] == 'read':
        del k_args['task']
        response = tm.todo_read(session_id=k_args['session_id'])
        return response
    if k_args['task'] == 'update':
        del k_args['task']
        del k_args['todoids']
        response = tm.todo_write(**k_args)
        return response
    if k_args['task'] == 'complete_all':
        del k_args['task']
        read_res = tm.todo_read(session_id=k_args['session_id'])
        for i in json.loads(read_res)['todos']:
            if i['status'] != 'completed':
                del k_args['todo_id']
                k_args['todo_id'] = i['id']
                update_res = tm.todo_write(**k_args) 
        return update_res 


"""



