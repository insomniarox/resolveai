"""Keep downloadable examples compatible with the actual comparison contract."""

import json
from pathlib import Path

from resolve_ai.comparison_models import ComparisonInput
from resolve_ai.comparison_reasoner import cause_questions, evidence_questions

ROOT = Path(__file__).resolve().parents[1]


def test_comparison_packages_fit_production_contract_and_context_budget():
    packages = json.loads((ROOT / "web/lib/data/comparison-packages.json").read_text())
    # Reserve 9 KB for three stored runbooks beyond the supplied documents.
    runbooks = [
        {
            "id": f"RUN-{i}",
            "title": "Stored runbook",
            "service": "svc",
            "content": "x" * 3000,
            "similarity_score": 0.5,
        }
        for i in range(3)
    ]
    for package in packages:
        request = ComparisonInput.model_validate(package["request"])
        state = {
            "incident": request.bundle.incident.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in request.bundle.evidence],
            "references": runbooks
            + [d.model_dump(mode="json") for d in request.bundle.knowledge_documents],
        }
        questions = [cause_questions(request.candidates)] + [
            evidence_questions(state, c) for c in request.candidates
        ]
        for question in questions:
            assert (
                len(
                    json.dumps(
                        {"state": state, "questions": question}, ensure_ascii=False
                    ).encode()
                )
                < 30_000
            ), package["id"]


def test_downloadable_schema_matches_server_contract():
    published = json.loads(
        (ROOT / "web/public/comparison-input.schema.json").read_text()
    )
    published.pop("$schema")
    published.pop("description")
    assert published == ComparisonInput.model_json_schema()
