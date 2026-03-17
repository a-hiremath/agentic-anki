"""Single structured-output LLM abstraction (Spec Section 12.3)."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from anki_pipeline.llm.parsing import extract_tool_use_input
from anki_pipeline.llm.retry import with_retry

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Anthropic client wrapper with structured output via tool-use.

    Usage::

        client = LLMClient(model="claude-opus-4-6")
        result = client.structured_call(
            output_schema=ExtractionResponse,
            system="You are ...",
            user="Extract ...",
            max_tokens=2048,
        )
    """

    def __init__(
        self,
        model: str = "claude-opus-4-6",
        api_key: str | None = None,
        max_retries: int = 1,
    ) -> None:
        import anthropic

        self.model = model
        self.max_retries = max_retries
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_calls: int = 0

    def usage_summary(self) -> dict[str, int]:
        """Return cumulative token usage statistics."""
        return {
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_calls": self._total_calls,
        }

    def structured_call(
        self,
        output_schema: type[T],
        system: str,
        user: str,
        max_tokens: int = 2048,
        tool_name: str | None = None,
        tool_description: str | None = None,
    ) -> T:
        """Make a structured LLM call using tool-use to enforce output schema.

        Returns a validated instance of `output_schema`.
        Retries up to `max_retries` on parse/schema failures.
        """
        name = tool_name or _schema_to_tool_name(output_schema)
        description = tool_description or f"Output a {output_schema.__name__} object"
        schema = _pydantic_to_json_schema(output_schema)

        tool_def = {
            "name": name,
            "description": description,
            "input_schema": schema,
        }

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._api_call(system, user, max_tokens, tool_def, name)
                tool_input = extract_tool_use_input(response)
                return output_schema.model_validate(tool_input)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "structured_call attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                if attempt >= self.max_retries:
                    break

        raise RuntimeError(
            f"structured_call failed after {self.max_retries + 1} attempts"
        ) from last_exc

    @with_retry(max_retries=3, initial_delay=2.0)
    def _api_call(
        self,
        system: str,
        user: str,
        max_tokens: int,
        tool_def: dict[str, Any],
        tool_choice_name: str,
    ) -> Any:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            tools=[tool_def],
            tool_choice={"type": "tool", "name": tool_choice_name},
        )
        # Track token usage
        usage = getattr(response, "usage", None)
        if usage:
            input_tok = getattr(usage, "input_tokens", 0)
            output_tok = getattr(usage, "output_tokens", 0)
            self._total_input_tokens += input_tok
            self._total_output_tokens += output_tok
            self._total_calls += 1
            logger.info(
                "LLM call: input=%d output=%d (cumulative: in=%d out=%d calls=%d)",
                input_tok, output_tok,
                self._total_input_tokens, self._total_output_tokens, self._total_calls,
            )
        return response


def _schema_to_tool_name(schema_class: type[BaseModel]) -> str:
    """Convert PascalCase class name to snake_case tool name."""
    import re
    name = schema_class.__name__
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return name.lower()


def _pydantic_to_json_schema(model_class: type[BaseModel]) -> dict[str, Any]:
    """Get the JSON schema for a Pydantic model, suitable for Anthropic tool input_schema."""
    schema = model_class.model_json_schema()
    # Anthropic requires the top-level to have "type": "object"
    # Pydantic generates this by default for BaseModel
    return schema
