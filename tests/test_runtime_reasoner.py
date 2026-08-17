"""Verify explicit runtime provider selection without making model requests."""

import pytest

from resolve_ai import runtime_reasoner
from resolve_ai.openai_model import generate_openai_runtime_hypothesis
from resolve_ai.openrouter_model import generate_openrouter_runtime_hypothesis
from resolve_ai.runtime_reasoner import (
    RuntimeReasonerConfigurationError,
    get_runtime_reasoner,
)


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch) -> None:
    """Keep developer secrets outside deterministic configuration tests."""
    monkeypatch.setattr(runtime_reasoner, "load_dotenv", lambda: None)


def test_selects_openrouter_with_fixed_model(monkeypatch) -> None:
    monkeypatch.setenv("RESOLVEAI_RUNTIME_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    reasoner = get_runtime_reasoner()

    assert reasoner.metadata.model == "openai/gpt-5.6-luna"
    assert reasoner.metadata.provider == "openrouter"
    assert reasoner.generate is generate_openrouter_runtime_hypothesis


def test_selects_direct_openai_without_changing_the_public_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RESOLVEAI_RUNTIME_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    reasoner = get_runtime_reasoner()

    assert reasoner.metadata.model == "gpt-5.6-luna"
    assert reasoner.metadata.provider == "openai"
    assert reasoner.generate is generate_openai_runtime_hypothesis


@pytest.mark.parametrize(
    ("provider", "key_name"),
    [("openrouter", "OPENROUTER_API_KEY"), ("openai", "OPENAI_API_KEY")],
)
def test_selected_provider_requires_its_own_key(
    monkeypatch,
    provider: str,
    key_name: str,
) -> None:
    monkeypatch.setenv("RESOLVEAI_RUNTIME_PROVIDER", provider)
    monkeypatch.delenv(key_name, raising=False)

    with pytest.raises(RuntimeReasonerConfigurationError, match=key_name):
        get_runtime_reasoner()


def test_rejects_missing_or_unknown_provider(monkeypatch) -> None:
    monkeypatch.delenv("RESOLVEAI_RUNTIME_PROVIDER", raising=False)
    with pytest.raises(RuntimeReasonerConfigurationError, match="must be one of"):
        get_runtime_reasoner()

    monkeypatch.setenv("RESOLVEAI_RUNTIME_PROVIDER", "automatic")
    with pytest.raises(RuntimeReasonerConfigurationError, match="must be one of"):
        get_runtime_reasoner()
