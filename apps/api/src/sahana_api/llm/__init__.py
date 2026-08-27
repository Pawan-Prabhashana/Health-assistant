"""LLM provider layer: role-based chat models over an OpenAI-compatible transport."""

from __future__ import annotations

from sahana_api.llm.base import (
    ChatModel,
    Completion,
    LLMError,
    LLMResponseError,
    LLMTimeoutError,
    Message,
    ProviderNotConfiguredError,
    Role,
    StructuredCompletion,
    StructuredParseError,
    Usage,
)
from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.health import make_llm_check
from sahana_api.llm.provider import ProviderClient
from sahana_api.llm.registry import ModelRegistry, build_model_registry
from sahana_api.llm.retry import RetryPolicy, is_transient, retry_after_seconds, run_with_policy
from sahana_api.llm.usage import estimate_cost

__all__ = [
    "ChatModel",
    "Completion",
    "FakeChatModel",
    "LLMError",
    "LLMResponseError",
    "LLMTimeoutError",
    "Message",
    "ModelRegistry",
    "ProviderClient",
    "ProviderNotConfiguredError",
    "RetryPolicy",
    "Role",
    "StructuredCompletion",
    "StructuredParseError",
    "Usage",
    "build_model_registry",
    "estimate_cost",
    "is_transient",
    "make_llm_check",
    "retry_after_seconds",
    "run_with_policy",
]
