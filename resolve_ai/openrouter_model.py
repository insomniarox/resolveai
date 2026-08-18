"""Run the concrete OpenAI reasoning baseline through OpenRouter."""

import os

from dotenv import load_dotenv
from openai import OpenAI

from resolve_ai.models import (
    Evidence,
    Hypothesis,
    Incident,
    RetrievedReferenceKnowledge,
)
from resolve_ai.openai_model import (
    MODEL_TIMEOUT_SECONDS,
    generate_openai_hypothesis,
    generate_openai_runtime_hypothesis,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_REASONING_MODEL = "openai/gpt-5.6-luna"


def generate_openrouter_hypothesis(
    incident: Incident,
    evidence: list[Evidence],
    retrieved_knowledge: list[RetrievedReferenceKnowledge],
    *,
    client: OpenAI | None = None,
    model: str = OPENROUTER_REASONING_MODEL,
) -> Hypothesis:
    """Use OpenRouter transport with the existing structured Luna reasoner."""
    if client is None:
        load_dotenv()
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY must be set in .env")
        openrouter_client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            timeout=MODEL_TIMEOUT_SECONDS,
            max_retries=0,
        )
    else:
        openrouter_client = client

    return generate_openai_hypothesis(
        incident,
        evidence,
        retrieved_knowledge,
        client=openrouter_client,
        model=model,
    )


def generate_openrouter_runtime_hypothesis(
    incident: Incident,
    evidence: list[Evidence],
    retrieved_knowledge: list[RetrievedReferenceKnowledge],
    *,
    client: OpenAI | None = None,
    model: str = OPENROUTER_REASONING_MODEL,
) -> Hypothesis:
    """Use OpenRouter transport for open-taxonomy runtime reasoning."""
    if client is None:
        load_dotenv()
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY must be set in .env")
        openrouter_client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            timeout=MODEL_TIMEOUT_SECONDS,
            max_retries=0,
        )
    else:
        openrouter_client = client

    return generate_openai_runtime_hypothesis(
        incident,
        evidence,
        retrieved_knowledge,
        client=openrouter_client,
        model=model,
    )
