"""Select the one server-side reasoner allowed for runtime investigations."""

import os
from dataclasses import dataclass
from enum import StrEnum

from dotenv import load_dotenv

from resolve_ai.models import ReasonerMetadata
from resolve_ai.openai_model import (
    OPENAI_REASONING_MODEL,
    generate_openai_runtime_hypothesis,
)
from resolve_ai.openrouter_model import (
    OPENROUTER_REASONING_MODEL,
    generate_openrouter_runtime_hypothesis,
)
from resolve_ai.reasoning import HypothesisGenerator

RUNTIME_PROVIDER_ENV = "RESOLVEAI_RUNTIME_PROVIDER"


class RuntimeProvider(StrEnum):
    """List the deliberately supported server-side inference transports."""

    OPENROUTER = "openrouter"
    OPENAI = "openai"


class RuntimeReasonerConfigurationError(Exception):
    """Report missing or invalid server-side provider configuration."""


@dataclass(frozen=True)
class ConfiguredRuntimeReasoner:
    """Pair the selected callable with safe metadata returned to clients."""

    metadata: ReasonerMetadata
    generate: HypothesisGenerator


def get_runtime_reasoner() -> ConfiguredRuntimeReasoner:
    """Resolve one explicit provider with no cross-provider or fake fallback."""
    load_dotenv()
    configured_value = os.environ.get(RUNTIME_PROVIDER_ENV, "").strip().lower()
    try:
        provider = RuntimeProvider(configured_value)
    except ValueError as error:
        supported = ", ".join(item.value for item in RuntimeProvider)
        raise RuntimeReasonerConfigurationError(
            f"{RUNTIME_PROVIDER_ENV} must be one of: {supported}"
        ) from error

    if provider == RuntimeProvider.OPENROUTER:
        _require_api_key("OPENROUTER_API_KEY")
        return ConfiguredRuntimeReasoner(
            metadata=ReasonerMetadata(
                provider=provider.value,
                model=OPENROUTER_REASONING_MODEL,
            ),
            generate=generate_openrouter_runtime_hypothesis,
        )

    _require_api_key("OPENAI_API_KEY")
    return ConfiguredRuntimeReasoner(
        metadata=ReasonerMetadata(
            provider=provider.value,
            model=OPENAI_REASONING_MODEL,
        ),
        generate=generate_openai_runtime_hypothesis,
    )


def _require_api_key(variable_name: str) -> None:
    """Fail before inference if the selected provider has no usable secret."""
    if not os.environ.get(variable_name, "").strip():
        raise RuntimeReasonerConfigurationError(
            f"{variable_name} is required for the selected runtime provider"
        )
