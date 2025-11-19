"""LLM API client for interacting with OpenRouter."""

from typing import List, Dict, Optional, Tuple
import logging
import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """Handles LLM API interactions."""

    def __init__(self, api_key: str, model: str, timeout: int = 60):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def call(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Tuple[Dict, Dict]:
        """Call LLM API and return response."""
        payload = {
            "model": self.model,
            "messages": messages
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            response = requests.post(
                url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            message = data['choices'][0]['message']

            logger.info(f"LLM Response: {message.get('content', '[tool call]')[:1000]}...")
            return data, message

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected API response format: {e}")
            raise
