"""Agent management for loading and executing specialized agents."""

from dataclasses import dataclass
from typing import List, Dict, Optional, Callable, Any
from pathlib import Path
import json
import logging
import yaml

from llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    name: str
    description: str
    example: str
    tools: List[str]
    system_prompt: str


class AgentManager:
    """Manages agent loading and execution."""

    def __init__(self, agent_directory: Path, llm_client: LLMClient,
                 tool_mapping: Dict, tool_schemas: Dict, max_iterations: int = 6):
        self.agent_directory = agent_directory
        self.llm_client = llm_client
        self.tool_mapping = tool_mapping
        self.tool_schemas = tool_schemas
        self.max_iterations = max_iterations
        self._agent_cache: Dict[str, AgentConfig] = {}

    def get_agent_names(self) -> List[str]:
        """Get list of available agent names."""
        if not self.agent_directory.exists():
            logger.warning(f"Agent directory not found: {self.agent_directory}")
            return []
        return json.dumps([
            f.stem for f in self.agent_directory.iterdir()
            if f.is_file() and f.suffix == '.md'
        ])

    def load_agent(self, name: str) -> AgentConfig:
        """Load agent configuration from file."""
        if name in self._agent_cache:
            return self._agent_cache[name]
        agent_path = self.agent_directory / f"{name}.md"
        if not agent_path.exists():
            available = ", ".join(self.get_agent_names())
            raise ValueError(f"Agent '{name}' not found. Available: {available}")
        content = agent_path.read_text(encoding='utf-8')
        parsed = self._parse_front_matter(content)
        front_matter = parsed['front_matter']
        config = AgentConfig(
            name=name,
            description=front_matter.get('description', ''),
            example=front_matter.get('example', ''),
            tools=front_matter.get('tools', '').split(', ') if front_matter.get('tools') else [], # Handle empty tools
            system_prompt=parsed['body']
        )
        self._agent_cache[name] = config
        return config

    def call_agent(self, name: str, prompt: str, system_message_callback: Optional[Callable] = None) -> str:
        """Execute an agent with the given prompt."""
        agent = self.load_agent(name)
        tools = [self.tool_schemas[tool_name] for tool_name in agent.tools
                 if tool_name in self.tool_schemas]
        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": prompt}
        ]
        iteration = 0
        responses = []

        tool_payload = tools if tools else None

        while iteration < self.max_iterations:
            iteration += 1
            log_msg = f"Agent '{name}' iteration {iteration}/{self.max_iterations}"
            logger.info(log_msg)
            if system_message_callback:
                system_message_callback(f"↪ Sub-agent '{name}' iteration {iteration}/{self.max_iterations}")

            _, message = self.llm_client.call(messages, tool_payload)
            messages.append(message)

            if 'tool_calls' in message and message['tool_calls']:
                for tool_call in message['tool_calls']:
                    tool_response = self._execute_tool_call(tool_call, system_message_callback, agent_name=name)
                    messages.append(tool_response)
            else:
                content=message.get('content', '').strip()
                if content:
                    responses.append(content)
                break

        if iteration >= self.max_iterations:
            logger.warning(f"Agent '{name}' reached max iterations")
            # Get one final response
            _, final_message = self.llm_client.call(messages, tool_payload)
            responses.append(final_message.get('content', ''))

        # Consolidate final response logic
        if not responses or 'tool_calls' in messages[-1]:
             # If the loop ended on tool calls, or max iterations, get a final summary
            logger.info("Getting final summary from agent.")
            final_messages_payload = [m for m in messages if m['role'] != 'system']
            final_messages_payload.insert(0, {"role": "system", "content": agent.system_prompt})

            # Ask model to summarize based on the conversation
            final_messages_payload.append({"role": "user", "content": "Based on our conversation and the tools used, provide the final answer to my original request."})

            _, final_message = self.llm_client.call(final_messages_payload, None) # No tools for final summary
            responses.append(final_message.get('content', ''))

        return "\n\n".join(filter(None, responses))

    def _execute_tool_call(self, tool_call: Dict, system_message_callback: Optional[Callable] = None, agent_name: str = "sub-agent") -> Dict:
        """Execute a tool call and return formatted response."""
        tool_name = tool_call['function']['name']
        arguments_str = tool_call['function']['arguments']

        tool_args = {}
        if arguments_str:
            try:
                tool_args = json.loads(arguments_str)
            except json.JSONDecodeError as e:
                print(f"Error: Failed to decode JSON arguments. String was: {arguments_str}")
                print(f"Exception: {e}")
                logger.error(f"Failed to decode tool args: {e}")

        log_msg = f"Calling tool: {tool_name} with args: {tool_args}"
        logger.info(log_msg)
        if system_message_callback:
            system_message_callback(f"↪ Sub-agent '{agent_name}' → Calling tool: {tool_name}")

        try:
            if tool_name not in self.tool_mapping:
                result = f"Error: Unknown tool '{tool_name}'"
            else:
                tool_fn = self.tool_mapping[tool_name]
                if tool_name == "call_agent":
                    # Pass the callback down to the next agent
                    tool_args['system_message_callback'] = system_message_callback
                    result = str(tool_fn(**tool_args))
                else:
                    # Standard tool call
                    result = str(tool_fn(**tool_args))

            log_msg = f"Tool result: {result[:500]}..."
            logger.info(log_msg)
            if system_message_callback:
                truncated_response = str(result)[:200]
                if len(str(result)) > 200:
                    truncated_response += "..."
                system_message_callback(f"↪ Sub-agent '{agent_name}' ✓ Success: {truncated_response}")

            return {
                "role": "tool",
                "tool_call_id": tool_call['id'],
                "content": result,
            }
        except Exception as e:
            log_msg = f"Tool execution failed: {e}"
            logger.error(log_msg, exc_info=True)
            if system_message_callback:
                system_message_callback(f"↪ Sub-agent '{agent_name}' ✗ Failed: {log_msg}", is_error=True)
            return {
                "role": "tool",
                "tool_call_id": tool_call['id'],
                "content": f"Error executing {tool_name}: {str(e)}",
            }

    @staticmethod
    def _parse_front_matter(content: str) -> Dict:
        """Parse YAML front matter from markdown."""
        import re
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
        if match:
            try:
                front_matter = yaml.safe_load(match.group(1))
                if front_matter is None:
                    front_matter = {}
            except yaml.YAMLError as e:
                logger.error(f"Error parsing YAML front matter: {e}")
                front_matter = {}
            return {
                'front_matter': front_matter,
                'body': match.group(2)
            }
        return {'front_matter': {}, 'body': content}
