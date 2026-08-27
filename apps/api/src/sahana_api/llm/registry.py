"""Role registry and factory.

The registry maps ``guardrail | router | synth`` to a configured ``ChatModel`` so
callers ask for a role, not a vendor. The factory selects real provider clients
or the deterministic fake from ``llm_mode``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sahana_api.config import Settings
from sahana_api.llm.base import ChatModel, ProviderNotConfiguredError, Role
from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.provider import ProviderClient

_ROLES: tuple[Role, ...] = ("guardrail", "router", "synth")


@dataclass(frozen=True)
class ModelRegistry:
    """Immutable role → model mapping."""

    models: dict[Role, ChatModel]

    def get_model(self, role: Role) -> ChatModel:
        """Return the model for ``role``.

        :raises ProviderNotConfiguredError: if the role has no configured model.
        """
        try:
            return self.models[role]
        except KeyError as exc:
            raise ProviderNotConfiguredError(f"no model configured for role '{role}'") from exc

    def configured_roles(self) -> frozenset[Role]:
        """Return the set of roles with a configured model."""
        return frozenset(self.models)

    async def aclose(self) -> None:
        """Close any provider clients holding HTTP connections."""
        for model in self.models.values():
            if isinstance(model, ProviderClient):
                await model.aclose()


@dataclass(frozen=True)
class _RoleSpec:
    role: Role
    model: str
    api_key: str | None
    base_url: str
    extra_headers: dict[str, str] | None


def _role_specs(settings: Settings) -> list[_RoleSpec]:
    """Build the provider spec for each role from settings."""
    openrouter_headers = {
        "HTTP-Referer": settings.openrouter_referer,
        "X-Title": settings.openrouter_title,
    }
    return [
        _RoleSpec(
            "guardrail",
            settings.guardrail_model,
            settings.groq_api_key,
            settings.groq_base_url,
            None,
        ),
        _RoleSpec(
            "router", settings.router_model, settings.groq_api_key, settings.groq_base_url, None
        ),
        _RoleSpec(
            "synth",
            settings.synth_model,
            settings.openrouter_api_key,
            settings.openrouter_base_url,
            openrouter_headers,
        ),
    ]


def build_model_registry(settings: Settings) -> ModelRegistry:
    """Build a :class:`ModelRegistry` from settings (fake or live per ``llm_mode``)."""
    if settings.llm_mode == "fake":
        return ModelRegistry(
            {role: FakeChatModel(role=role, model=f"fake-{role}") for role in _ROLES}
        )

    models: dict[Role, ChatModel] = {}
    for spec in _role_specs(settings):
        if spec.api_key is None:
            continue
        models[spec.role] = ProviderClient(
            role=spec.role,
            model=spec.model,
            api_key=spec.api_key,
            base_url=spec.base_url,
            prices=settings.model_prices,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            repair_attempts=settings.llm_structured_repair_attempts,
            extra_headers=spec.extra_headers,
        )
    return ModelRegistry(models)
