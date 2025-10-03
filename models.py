from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union, Literal, Any
from enum import Enum


class VerbosityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResponseFormat(BaseModel):
    type: Literal["json_object"]


class ToolFunction(BaseModel):
    name: str


class ToolChoice(BaseModel):
    type: Literal["function"]
    function: ToolFunction


class OpenRouterAPIParameters(BaseModel):
    """
    Pydantic model for OpenRouter API parameters.
    This model includes all the sampling parameters that can be used
    to configure OpenRouter API requests for language model generation.
    """
    temperature: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Controls variety in responses. Lower = more predictable, higher = more diverse"
    )
    top_p: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling - limits model choices to top tokens with cumulative probability P"
    )
    top_k: Optional[int] = Field(
        default=0,
        ge=0,
        description="Limits model choice to top K tokens at each step. 0 = disabled"
    )
    frequency_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Reduces repetition based on token frequency in input"
    )
    presence_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Reduces repetition of tokens already used in input"
    )
    repetition_penalty: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Reduces repetition from input. Higher = less repetition"
    )
    min_p: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum probability for token consideration, relative to most likely token"
    )
    top_a: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Dynamic filtering based on probability of most likely token"
    )
    seed: Optional[int] = Field(
        default=None,
        description="Seed for deterministic sampling"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of tokens to generate"
    )
    logit_bias: Optional[Dict[str, float]] = Field(
        default=None,
        description="Map of token IDs to bias values (-100 to 100)"
    )
    logprobs: Optional[bool] = Field(
        default=None,
        description="Whether to return log probabilities of output tokens"
    )
    top_logprobs: Optional[int] = Field(
        default=None,
        ge=0,
        le=20,
        description="Number of most likely tokens to return with log probabilities"
    )
    response_format: Optional[ResponseFormat] = Field(
        default=None,
        description="Forces specific output format, e.g., JSON mode"
    )
    structured_outputs: Optional[bool] = Field(
        default=None,
        description="Whether model can return structured outputs using response_format json_schema"
    )
    stop: Optional[List[str]] = Field(
        default=None,
        description="Array of tokens that will stop generation"
    )
    tools: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Tool calling parameter following OpenAI's tool calling format"
    )
    tool_choice: Optional[Union[str, ToolChoice]] = Field(
        default=None,
        description="Controls which tool is called: 'none', 'auto', 'required', or specific tool"
    )
    parallel_tool_calls: Optional[bool] = Field(
        default=True,
        description="Whether to enable parallel function calling during tool use"
    )
    verbosity: Optional[VerbosityLevel] = Field(
        default=VerbosityLevel.MEDIUM,
        description="Controls verbosity and length of model response"
    )
    reasoning: Optional[ReasoningLevel] = Field(
        default=None,
        description="Controls the reasoning level of model response"
    )