"""Evaluate Phase 7.6 causal correctness without normalizing generated prose.

The deterministic layer measures retrieval and cleanup for four preregistered
runtime cases. The optional live layer retains the raw label and diagnosis prose,
then produces a label-hidden packet for a small human review. Human judgments
remain outside this program rather than being approximated with aliases or a
second model.
"""

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from evals.evaluate_runtime_ingestion import (
    MetricScore,
    RuntimeIngestionCase,
    RuntimeReasoningResult,
    RuntimeRetrievalResult,
    calculate_reasoning_metrics,
    evaluate_runtime_reasoning_cases,
    evaluate_runtime_retrieval_case,
    print_reasoning_report,
    snapshot_frozen_runbook_results,
    verify_frozen_artifact_hashes,
)
from resolve_ai.models import InvestigationStatus
from resolve_ai.runtime_reasoner import RUNTIME_PROVIDER_ENV, get_runtime_reasoner

CASES_PATH = Path(__file__).with_name("runtime_contract_cases.json")
RUNTIME_CONTRACT_CASES_SHA256 = (
    "500cdffc2c50b314beb322b0cfef72167a6932f05a1828a53beac5d125e90065"
)


class ContractPressure(StrEnum):
    """Name each retrieval or reasoning pressure selected before model runs."""

    LONG_DOCUMENT = "long_document"
    CLOSE_DISTRACTOR = "close_distractor"
    NEAR_DUPLICATE = "near_duplicate"
    CONFLICTING_GUIDANCE = "conflicting_guidance"


class CausalContract(BaseModel):
    """Provide a human-readable rubric rather than generated-label aliases."""

    affected_component: str = Field(min_length=1)
    failure_mode: str = Field(min_length=1)
    operational_effect: str = Field(min_length=1)
    forbidden_claims: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_forbidden_claims(self) -> Self:
        """Keep every forbidden claim non-empty and unique within one case."""
        normalized = [claim.strip() for claim in self.forbidden_claims]
        if any(not claim for claim in normalized):
            raise ValueError("forbidden claims must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("forbidden claims must be unique")
        return self


class RuntimeContractCase(RuntimeIngestionCase):
    """Add preregistered pressure and prose-review fields to one runtime case."""

    pressures: list[ContractPressure] = Field(min_length=1)
    causal_contract: CausalContract

    @model_validator(mode="after")
    def validate_pressures(self) -> Self:
        """Reject repeated pressure labels within one case."""
        if len(self.pressures) != len(set(self.pressures)):
            raise ValueError("contract pressures must be unique within a case")
        return self


class RuntimeContractDataset(BaseModel):
    """Represent the four separately frozen Phase 7.6 cases."""

    cases: list[RuntimeContractCase]

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        """Protect dataset size, identities, and preregistered pressure coverage."""
        if len(self.cases) != 4:
            raise ValueError("runtime contract evaluation requires four cases")

        groups = {
            "case": [case.id for case in self.cases],
            "incident": [case.bundle.incident.id for case in self.cases],
            "Evidence": [
                item.id for case in self.cases for item in case.bundle.evidence
            ],
            "runtime document": [
                item.id
                for case in self.cases
                for item in case.bundle.knowledge_documents
            ],
        }
        for name, identifiers in groups.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{name} IDs must be unique across contract cases")

        observed_pressures = {
            pressure for case in self.cases for pressure in case.pressures
        }
        if observed_pressures != set(ContractPressure):
            raise ValueError("contract cases must cover every planned pressure")

        long_cases = [
            case
            for case in self.cases
            if ContractPressure.LONG_DOCUMENT in case.pressures
        ]
        if len(long_cases) != 1:
            raise ValueError("exactly one case must own the long-document pressure")
        longest_content = max(
            len(document.content)
            for document in long_cases[0].bundle.knowledge_documents
        )
        if longest_content < 1_500:
            raise ValueError("the long-document case requires at least 1500 characters")

        statuses = {case.ground_truth.expected_status for case in self.cases}
        if statuses != {
            InvestigationStatus.DIAGNOSED,
            InvestigationStatus.INCONCLUSIVE,
        }:
            raise ValueError("contract cases require diagnosed and inconclusive truth")
        return self


@dataclass(frozen=True)
class ContractDeterministicReport:
    """Keep new-case retrieval observations beside frozen-corpus protection."""

    retrieval_results: list[RuntimeRetrievalResult]
    frozen_runbooks_before: dict[str, list[str]]
    frozen_runbooks_after: dict[str, list[str]]

    @property
    def runtime_document_top1_accuracy(self) -> MetricScore:
        """Score only document requirements preregistered as Top-1."""
        expectations = [
            (result, expectation)
            for result in self.retrieval_results
            for expectation in result.case.ground_truth.required_knowledge_documents
            if expectation.max_rank == 1
        ]
        return MetricScore(
            numerator=sum(
                bool(result.retrieved_document_ids)
                and result.retrieved_document_ids[0] == expectation.document_id
                for result, expectation in expectations
            ),
            denominator=len(expectations),
        )

    @property
    def required_document_top3_recall(self) -> MetricScore:
        """Score every required runtime document against supplied Top-3."""
        expectations = [
            (result, expectation)
            for result in self.retrieval_results
            for expectation in result.case.ground_truth.required_knowledge_documents
        ]
        return MetricScore(
            numerator=sum(
                expectation.document_id in result.retrieved_document_ids[:3]
                for result, expectation in expectations
            ),
            denominator=len(expectations),
        )

    @property
    def retained_row_count(self) -> int:
        """Count evaluation-owned rows left after deterministic retrieval."""
        return sum(result.retained_scope_rows for result in self.retrieval_results)

    @property
    def safety_gates_pass(self) -> bool:
        """Require cleanup, stable runbooks, and successful retrieval operations."""
        return (
            self.retained_row_count == 0
            and self.frozen_runbooks_before == self.frozen_runbooks_after
            and not any(result.error for result in self.retrieval_results)
        )


@dataclass(frozen=True)
class BlindReviewItem:
    """Expose prose and rubric without provider, repeat, case, or label identity."""

    review_id: str
    probable_root_cause: str
    affected_component: str
    failure_mode: str
    operational_effect: str
    forbidden_claims: list[str]


def _sha256(path: Path) -> str:
    """Return the byte-level digest used by the Phase 7.6 dataset guard."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_contract_artifact_hashes() -> None:
    """Protect the new dataset and every Phase 7.4 or legacy artifact."""
    verify_frozen_artifact_hashes()
    if _sha256(CASES_PATH) != RUNTIME_CONTRACT_CASES_SHA256:
        raise RuntimeError("runtime contract dataset hash does not match")


def load_contract_dataset(
    path: Path = CASES_PATH,
) -> RuntimeContractDataset:
    """Load and validate the preregistered Phase 7.6 cases."""
    raw_dataset = json.loads(path.read_text(encoding="utf-8"))
    return RuntimeContractDataset.model_validate(raw_dataset)


def evaluate_contract_deterministic_layer(
    database_url: str,
    dataset: RuntimeContractDataset,
) -> ContractDeterministicReport:
    """Measure new-case retrieval while proving frozen runbook order is stable."""
    before = snapshot_frozen_runbook_results(database_url)
    retrieval_results = [
        evaluate_runtime_retrieval_case(database_url, case) for case in dataset.cases
    ]
    after = snapshot_frozen_runbook_results(database_url)
    return ContractDeterministicReport(
        retrieval_results=retrieval_results,
        frozen_runbooks_before=before,
        frozen_runbooks_after=after,
    )


def build_blind_review_items(
    results: list[RuntimeReasoningResult],
    dataset: RuntimeContractDataset,
) -> list[BlindReviewItem]:
    """Build diagnosed prose-review items without revealing run identities."""
    contracts = {case.id: case.causal_contract for case in dataset.cases}
    items: list[BlindReviewItem] = []
    for result in results:
        if result.probable_root_cause is None:
            continue
        contract = contracts[result.case.id]
        opaque_id = hashlib.sha256(
            f"{result.case.id}:{result.repeat}".encode()
        ).hexdigest()[:10]
        items.append(
            BlindReviewItem(
                review_id=f"review-{opaque_id}",
                probable_root_cause=result.probable_root_cause,
                affected_component=contract.affected_component,
                failure_mode=contract.failure_mode,
                operational_effect=contract.operational_effect,
                forbidden_claims=list(contract.forbidden_claims),
            )
        )
    return sorted(items, key=lambda item: item.review_id)


def write_blind_review_packet(
    path: Path,
    items: list[BlindReviewItem],
) -> None:
    """Write a plain Markdown worksheet for a human reviewer."""
    sections = [
        "# Phase 7.6 blind causal review",
        "",
        "The reviewer should not inspect the full evaluator output first. For each",
        "item, mark the three facets correct, absent, or contradicted. Record whether",
        "the prose makes any forbidden claim. The generated label, provider, repeat,",
        "and case identity are deliberately omitted.",
    ]
    for item in items:
        forbidden = "\n".join(f"- {claim}" for claim in item.forbidden_claims)
        sections.extend(
            [
                "",
                f"## {item.review_id}",
                "",
                item.probable_root_cause,
                "",
                "Expected causal facets:",
                "",
                f"- Affected component: {item.affected_component}",
                f"- Failure mode: {item.failure_mode}",
                f"- Operational effect: {item.operational_effect}",
                "",
                "Forbidden claims:",
                "",
                forbidden,
                "",
                "Review:",
                "",
                "- Affected component: [correct | absent | contradicted]",
                "- Failure mode: [correct | absent | contradicted]",
                "- Operational effect: [correct | absent | contradicted]",
                "- Forbidden claim present: [yes | no]",
                "- Notes:",
            ]
        )
    path.write_text("\n".join(sections) + "\n", encoding="utf-8")


def _format_metric(metric: MetricScore) -> str:
    """Render a numerator and denominator without hiding an empty denominator."""
    if metric.value is None:
        return f"{metric.numerator}/{metric.denominator} (N/A)"
    return f"{metric.numerator}/{metric.denominator} ({metric.value:.0%})"


def print_contract_deterministic_report(
    report: ContractDeterministicReport,
) -> None:
    """Print case-level retrieval results and aggregate deterministic gates."""
    print("Phase 7.6 deterministic contract evaluation")
    for result in report.retrieval_results:
        documents = ", ".join(result.retrieved_document_ids) or "none"
        scores = ", ".join(f"{score:.4f}" for score in result.similarity_scores)
        print(
            f"{result.case.id}: documents={documents} scores={scores or 'none'} "
            f"retained_rows={result.retained_scope_rows}"
        )
        if result.error:
            print(f"  error={result.error}")
    print(
        "Runtime-document Top-1 accuracy: "
        f"{_format_metric(report.runtime_document_top1_accuracy)}"
    )
    print(
        "Required-document Top-3 recall: "
        f"{_format_metric(report.required_document_top3_recall)}"
    )
    print(f"Post-cleanup retained row count: {report.retained_row_count}")
    print(
        "Frozen runbook results unchanged: "
        f"{report.frozen_runbooks_before == report.frozen_runbooks_after}"
    )
    print(
        f"Deterministic safety gates: {'PASS' if report.safety_gates_pass else 'FAIL'}"
    )


def main() -> None:
    """Run deterministic gates and optionally produce the capped live baseline."""
    parser = argparse.ArgumentParser(
        description="Evaluate the frozen Phase 7.6 runtime causal contract."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--live-provider", choices=("openrouter", "openai"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--review-packet", type=Path)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 5:
        parser.error("--repeats must be between 1 and 5")
    if args.review_packet is not None and args.live_provider is None:
        parser.error("--review-packet requires --live-provider")

    verify_contract_artifact_hashes()
    dataset = load_contract_dataset()
    deterministic_report = evaluate_contract_deterministic_layer(
        args.database_url,
        dataset,
    )
    print_contract_deterministic_report(deterministic_report)
    if not deterministic_report.safety_gates_pass:
        raise SystemExit(1)

    if args.live_provider:
        os.environ[RUNTIME_PROVIDER_ENV] = args.live_provider
        configured = get_runtime_reasoner()
        reasoning_results = evaluate_runtime_reasoning_cases(
            database_url=args.database_url,
            cases=list(dataset.cases),
            hypothesis_generator=configured.generate,
            reasoner=configured.metadata,
            repeats=args.repeats,
        )
        print_reasoning_report(reasoning_results)
        metrics = calculate_reasoning_metrics(reasoning_results)
        if metrics.accepted_unsupported_citation_count or metrics.retained_row_count:
            raise SystemExit(1)

        if args.review_packet is not None:
            items = build_blind_review_items(reasoning_results, dataset)
            write_blind_review_packet(args.review_packet, items)
            print(f"Blind review packet: {args.review_packet}")


if __name__ == "__main__":
    main()
