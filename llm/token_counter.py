"""Token counting utilities for LLM API usage tracking."""

import tiktoken


def estimate_tokens(text: str, model: str = "gpt-5-nano") -> int:
    '''Count exact tokens using tiktoken.'''
    if not text:
        return 0
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


class TokenCounter:
    """Tracks input and output tokens for LLM API calls."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all counters to zero."""
        self.input_tokens = 0
        self.output_tokens = 0
        self.api_calls = 0

    def add_input(self, tokens: int):
        """Add to input token count."""
        self.input_tokens += tokens

    def add_output(self, tokens: int):
        """Add to output token count."""
        self.output_tokens += tokens

    def increment_call(self):
        """Increment API call counter."""
        self.api_calls += 1

    def get_summary(self) -> str:
        """Get a formatted summary of token usage."""
        total = self.input_tokens + self.output_tokens
        return (
            f"📊 Token Usage Summary:\n"
            f"   • Input tokens: {self.input_tokens:,}\n"
            f"   • Output tokens: {self.output_tokens:,}\n"
            f"   • Total tokens: {total:,}\n"
            f"   • API calls: {self.api_calls}"
        )

    def get_dict(self) -> dict:
        """Get token counts as dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "api_calls": self.api_calls
        }
