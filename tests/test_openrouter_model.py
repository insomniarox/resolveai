"""Test the concrete OpenRouter surface without network requests."""

from types import SimpleNamespace

import pytest

from resolve_ai import openrouter_model
from resolve_ai.fixtures import get_incident_context
from resolve_ai.investigation import inspect_deployments, inspect_logs
from resolve_ai.models import InvestigationStatus, RootCauseLabel
from resolve_ai.openai_model import MODEL_TIMEOUT_SECONDS, OpenAIReasoningDecision
from resolve_ai.openrouter_model import (
    OPENROUTER_BASE_URL,
    OPENROUTER_REASONING_MODEL,
    generate_openrouter_hypothesis,
)


class FakeResponses:
    """Return one parsed decision while retaining the SDK call arguments."""

    def __init__(self, decision: OpenAIReasoningDecision) -> None:
        self.decision = decision
        self.call: dict = {}

    def parse(self, **kwargs):
        self.call = kwargs
        return SimpleNamespace(output_parsed=self.decision)


class FakeOpenRouterClient:
    """Expose only the Responses operation used by the reasoner."""

    def __init__(self, decision: OpenAIReasoningDecision) -> None:
        self.responses = FakeResponses(decision)


def _reasoning_inputs():
    context = get_incident_context("INC-001")
    assert context is not None
    evidence = inspect_logs(context) + inspect_deployments(context)
    decision = OpenAIReasoningDecision(
        status=InvestigationStatus.DIAGNOSED,
        root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        probable_root_cause="The reduced pool caused connection timeouts.",
        cited_evidence_ids=["LOG-001"],
        confidence=0.88,
        recommended_remediation="Restore the previous pool size.",
    )
    return context.incident, evidence, [], decision


def test_openrouter_reasoner_uses_openrouter_luna_model() -> None:
    incident, evidence, runbooks, decision = _reasoning_inputs()
    client = FakeOpenRouterClient(decision)

    generate_openrouter_hypothesis(
        incident,
        evidence,
        runbooks,
        client=client,
    )

    assert client.responses.call["model"] == OPENROUTER_REASONING_MODEL
    assert client.responses.call["text_format"] is OpenAIReasoningDecision


def test_default_openrouter_client_loads_dotenv_and_uses_explicit_surface(
    monkeypatch,
) -> None:
    incident, evidence, runbooks, decision = _reasoning_inputs()
    client = FakeOpenRouterClient(decision)
    calls: list[object] = []

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr(
        openrouter_model,
        "load_dotenv",
        lambda: calls.append("load_dotenv"),
    )
    monkeypatch.setattr(
        openrouter_model,
        "OpenAI",
        lambda **kwargs: calls.append(kwargs) or client,
    )

    generate_openrouter_hypothesis(incident, evidence, runbooks)

    assert calls == [
        "load_dotenv",
        {
            "base_url": OPENROUTER_BASE_URL,
            "api_key": "test-openrouter-key",
            "timeout": MODEL_TIMEOUT_SECONDS,
            "max_retries": 0,
        },
    ]


def test_openrouter_reasoner_requires_its_own_api_key(monkeypatch) -> None:
    incident, evidence, runbooks, _ = _reasoning_inputs()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(openrouter_model, "load_dotenv", lambda: None)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        generate_openrouter_hypothesis(incident, evidence, runbooks)
