"""OpenAI-compatible provider client implementing ``ChatModel``.

Both Groq and OpenRouter expose OpenAI-compatible APIs, so a single async
transport (the ``openai`` ``AsyncOpenAI`` client) serves all three roles,
configured per provider with a different ``base_url``, API key, and (for
OpenRouter) attribution headers. See ADR 0009.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from time import perf_counter

from openai import AsyncOpenAI, omit
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject
from pydantic import BaseModel, ValidationError

from sahana_api.config import ModelPrice
from sahana_api.llm.base import (
    ChatModel,
    Completion,
    LLMResponseError,
    Message,
    Role,
    StreamCompleted,
    StreamEvent,
    StructuredCompletion,
    StructuredParseError,
    TextDelta,
    Usage,
)
from sahana_api.llm.retry import RetryPolicy, run_with_policy
from sahana_api.llm.usage import estimate_cost, log_usage
from sahana_api.logging import get_logger

_logger = get_logger("sahana_api.llm.provider")

_JSON_FORMAT: ResponseFormatJSONObject = {"type": "json_object"}

_STRUCTURED_SYSTEM = (
    "You must respond with a single JSON object that conforms exactly to this JSON "
    "Schema. Output only the JSON object, with no prose and no code fences.\n"
    "JSON Schema:\n{schema}"
)
_REPAIR_SYSTEM = (
    "Your previous response could not be parsed: {error}. Respond again with only a "
    "single JSON object that conforms to the schema."
)


def _to_openai_message(message: Message) -> ChatCompletionMessageParam:
    """Convert a :class:`Message` to the OpenAI message param TypedDict."""
    if message.role == "system":
        return {"role": "system", "content": message.content}
    if message.role == "assistant":
        return {"role": "assistant", "content": message.content}
    return {"role": "user", "content": message.content}


def _strip_code_fences(text: str) -> str:
    """Strip a leading/trailing Markdown code fence if the model added one."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()


class ProviderClient(ChatModel):
    """A ``ChatModel`` backed by an OpenAI-compatible provider."""

    def __init__(
        self,
        *,
        role: Role,
        model: str,
        api_key: str,
        base_url: str,
        prices: dict[str, ModelPrice],
        timeout: float,
        max_retries: int,
        repair_attempts: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._role = role
        self._model = model
        self._prices = prices
        self._timeout = timeout
        self._repair_attempts = repair_attempts
        self._extra_headers = extra_headers
        self._policy = RetryPolicy(max_retries=max_retries)
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            default_headers=extra_headers,
        )

    @property
    def model(self) -> str:
        return self._model

    def _params(self, messages: Sequence[Message]) -> list[ChatCompletionMessageParam]:
        return [_to_openai_message(message) for message in messages]

    async def _create(
        self,
        messages: Sequence[Message],
        *,
        temperature: float,
        max_tokens: int | None,
        json_mode: bool,
        event: str,
    ) -> Completion:
        """One completion call, wrapped in the retry policy, with usage accounting."""
        started = perf_counter()

        async def _call() -> ChatCompletion:
            return await self._client.chat.completions.create(
                model=self._model,
                messages=self._params(messages),
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else omit,
                response_format=_JSON_FORMAT if json_mode else omit,
                extra_headers=self._extra_headers,
            )

        response = await run_with_policy(
            _call, policy=self._policy, timeout=self._timeout, event=event
        )
        latency_ms = round((perf_counter() - started) * 1000, 1)
        return self._to_completion(response, latency_ms)

    def _to_completion(self, response: ChatCompletion, latency_ms: float) -> Completion:
        if not response.choices:
            raise LLMResponseError(f"{self._role} returned no choices")
        choice = response.choices[0]
        raw = response.usage
        prompt_tokens = raw.prompt_tokens if raw else 0
        completion_tokens = raw.completion_tokens if raw else 0
        total_tokens = raw.total_tokens if raw else prompt_tokens + completion_tokens
        usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimate_cost(
                self._prices, self._model, prompt_tokens, completion_tokens
            ),
            latency_ms=latency_ms,
        )
        log_usage(self._role, self._model, usage)
        return Completion(
            text=choice.message.content or "",
            model=self._model,
            finish_reason=choice.finish_reason,
            usage=usage,
        )

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> Completion:
        return await self._create(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
            event=f"llm.{self._role}.complete",
        )

    async def complete_structured[T: BaseModel](
        self,
        messages: Sequence[Message],
        schema: type[T],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> StructuredCompletion[T]:
        schema_json = json.dumps(schema.model_json_schema())
        conversation: list[Message] = [
            Message("system", _STRUCTURED_SYSTEM.format(schema=schema_json)),
            *messages,
        ]

        last_error: Exception | None = None
        for attempt in range(self._repair_attempts + 1):
            completion = await self._create(
                conversation,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
                event=f"llm.{self._role}.structured",
            )
            try:
                value = schema.model_validate_json(_strip_code_fences(completion.text))
            except (ValidationError, ValueError) as exc:
                last_error = exc
                if attempt >= self._repair_attempts:
                    break
                conversation = [
                    *conversation,
                    Message("assistant", completion.text),
                    Message("system", _REPAIR_SYSTEM.format(error=str(exc))),
                ]
                continue
            return StructuredCompletion(
                value=value,
                raw_text=completion.text,
                model=self._model,
                usage=completion.usage,
            )

        raise StructuredParseError(
            f"{self._role} structured output failed after {self._repair_attempts} repair attempt(s)"
        ) from last_error

    async def stream_events(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield deltas then usage. Streams are not retried (a partial stream is unsafe)."""
        started = perf_counter()
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=self._params(messages),
            temperature=temperature,
            max_tokens=max_tokens if max_tokens is not None else omit,
            stream=True,
            stream_options={"include_usage": True},
            extra_headers=self._extra_headers,
        )
        raw_usage = None
        deltas = 0
        async for chunk in stream:
            if chunk.usage is not None:
                raw_usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                deltas += 1
                yield TextDelta(delta)

        latency_ms = round((perf_counter() - started) * 1000, 1)
        usage: Usage | None = None
        if raw_usage is not None:
            usage = Usage(
                prompt_tokens=raw_usage.prompt_tokens,
                completion_tokens=raw_usage.completion_tokens,
                total_tokens=raw_usage.total_tokens,
                estimated_cost_usd=estimate_cost(
                    self._prices, self._model, raw_usage.prompt_tokens, raw_usage.completion_tokens
                ),
                latency_ms=latency_ms,
            )
            log_usage(self._role, self._model, usage)
        else:
            _logger.info(f"llm.{self._role}.stream.completed", latency_ms=latency_ms, deltas=deltas)
        yield StreamCompleted(usage=usage)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()
