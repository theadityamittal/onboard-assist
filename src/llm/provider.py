"""LLM provider interface and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModelRole(Enum):
    """Identifies the purpose of an LLM call for routing."""

    REASONING = "reasoning"
    GENERATION = "generation"


@dataclass(frozen=True)
class LLMResponse:
    """Immutable response from an LLM invocation."""

    text: str
    input_tokens: int
    output_tokens: int
    model_id: str

    def estimated_cost(
        self, *, input_price_per_1m: float, output_price_per_1m: float
    ) -> float:
        """Calculate estimated cost in USD."""
        input_cost = (self.input_tokens / 1_000_000) * input_price_per_1m
        output_cost = (self.output_tokens / 1_000_000) * output_price_per_1m
        return round(input_cost + output_cost, 8)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def invoke(
        self,
        *,
        messages: list[dict[str, Any]],
        model_id: str,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send messages to an LLM and return the response.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model_id: The model identifier to use.
            max_tokens: Maximum output tokens.

        Returns:
            LLMResponse with text, token counts, and model_id.
        """
