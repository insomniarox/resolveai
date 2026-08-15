"""Evaluate end-to-end investigations against frozen synthetic ground truth.

This evaluator measures application behavior; it is not a regression test that
requires the current fake to solve every case. Each exception is recorded as a
case-level system failure so one broken investigation does not hide later cases.
"""

import argparse
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, model_validator

from resolve_ai.fake_model import generate_fake_hypothesis
from resolve_ai.investigation import (
    UnknownEvidenceError,
    inspect_deployments,
    inspect_logs,
    investigate_incident,
)
from resolve_ai.models import (
    Evidence,
    Hypothesis,
    Incident,
    IncidentContext,
    InvestigationResult,
    InvestigationStatus,
    RetrievedRunbook,
    RootCauseLabel,
)
from resolve_ai.reasoning import HypothesisGenerator

BenchmarkSlice = Literal["core", "retrieval-dependent", "combined"]

CORE_CASES_PATH = Path(__file__).with_name("investigation_cases.json")
RETRIEVAL_DEPENDENT_CASES_PATH = Path(__file__).with_name(
    "investigation_retrieval_cases.json"
)


class RemediationLabel(StrEnum):
    """Store remediation intent for later evaluation without scoring prose."""

    RESTORE_PREVIOUS_CONNECTION_POOL_SIZE = "restore_previous_connection_pool_size"
    ROTATE_EXPIRED_CLIENT_CERTIFICATE = "rotate_expired_client_certificate"
    RESOLVE_BLOCKING_TRANSACTION = (
        "resolve_blocking_transaction_and_reduce_transaction_scope"
    )
    CORRECT_UPSTREAM_CERTIFICATE_IDENTITY = "correct_upstream_certificate_identity"
    RESTORE_OR_FAIL_OVER_PROVIDER = "restore_or_fail_over_notification_provider"
    RESTORE_NOTIFICATION_WORKER_CAPACITY = "restore_notification_worker_capacity"


class CaseOutcome(StrEnum):
    """Distinguish answer quality from execution failure at case level."""

    CORRECT_ANSWER = "correct_answer"
    CORRECT_WITH_EXTRANEOUS_EVIDENCE = "correct_with_extraneous_evidence"
    CORRECT_INCONCLUSIVE = "correct_inconclusive"
    INCORRECT_ANSWER = "incorrect_answer"
    UNSUPPORTED_ANSWER = "unsupported_answer"
    SYSTEM_FAILURE = "system_failure"


class InvestigationGroundTruth(BaseModel):
    """Describe model-independent expectations for one incident."""

    expected_status: InvestigationStatus
    root_cause_label: RootCauseLabel | None
    required_supporting_evidence_ids: list[str]
    acceptable_supporting_evidence_ids: list[str]
    relevant_runbook_ids: list[str]
    remediation_label: RemediationLabel | None
    prohibited_root_cause_labels: list[RootCauseLabel]

    @model_validator(mode="after")
    def validate_ground_truth(self) -> Self:
        """Enforce consistent diagnosed and inconclusive expectations."""
        required = set(self.required_supporting_evidence_ids)
        acceptable = set(self.acceptable_supporting_evidence_ids)

        if len(required) != len(self.required_supporting_evidence_ids):
            raise ValueError("required supporting evidence IDs must be unique")
        if len(acceptable) != len(self.acceptable_supporting_evidence_ids):
            raise ValueError("acceptable supporting evidence IDs must be unique")
        if not required <= acceptable:
            raise ValueError("required supporting evidence must also be acceptable")
        if not self.relevant_runbook_ids:
            raise ValueError("at least one relevant runbook ID is required")
        if self.root_cause_label in self.prohibited_root_cause_labels:
            raise ValueError("expected root cause cannot also be prohibited")

        if self.expected_status == InvestigationStatus.DIAGNOSED:
            if self.root_cause_label is None:
                raise ValueError("diagnosed cases require a root-cause label")
            if self.remediation_label is None:
                raise ValueError("diagnosed cases require a remediation label")
            if not required:
                raise ValueError("diagnosed cases require supporting evidence")
        else:
            if self.root_cause_label is not None:
                raise ValueError("inconclusive cases cannot have a root-cause label")
            if self.remediation_label is not None:
                raise ValueError("inconclusive cases cannot have a remediation label")
            if required or acceptable:
                raise ValueError("inconclusive cases cannot have supporting evidence")

        return self


class InvestigationBenchmarkCase(BaseModel):
    """Keep a complete frozen incident beside its independently labeled truth."""

    id: str
    context: IncidentContext
    ground_truth: InvestigationGroundTruth

    @model_validator(mode="after")
    def validate_evidence_references(self) -> Self:
        """Require every labeled citation to exist after evidence collection."""
        evidence = inspect_logs(self.context) + inspect_deployments(self.context)
        available_ids = {item.id for item in evidence}
        labeled_ids = set(self.ground_truth.acceptable_supporting_evidence_ids)
        unknown_ids = sorted(labeled_ids - available_ids)
        if unknown_ids:
            unknown = ", ".join(unknown_ids)
            raise ValueError(f"ground truth references unknown evidence: {unknown}")
        return self


@dataclass(frozen=True)
class InvestigationCaseResult:
    """Record one completed or failed benchmark investigation."""

    case: InvestigationBenchmarkCase
    actual_status: InvestigationStatus | None
    predicted_root_cause_label: RootCauseLabel | None
    cited_evidence_ids: list[str]
    outcome: CaseOutcome
    error: str | None = None

    @property
    def status_correct(self) -> bool:
        """Return whether a completed result has the expected status."""
        return self.actual_status == self.case.ground_truth.expected_status

    @property
    def root_cause_correct(self) -> bool:
        """Return whether a diagnosed case has the expected normalized cause."""
        return (
            self.actual_status == InvestigationStatus.DIAGNOSED
            and self.case.ground_truth.expected_status == InvestigationStatus.DIAGNOSED
            and self.predicted_root_cause_label
            == self.case.ground_truth.root_cause_label
        )

    @property
    def acceptable_citation_count(self) -> int:
        """Count predicted citations allowed by the benchmark."""
        predicted = set(self.cited_evidence_ids)
        acceptable = set(self.case.ground_truth.acceptable_supporting_evidence_ids)
        return len(predicted & acceptable)

    @property
    def required_citation_count(self) -> int:
        """Count required citations supplied by the investigation."""
        predicted = set(self.cited_evidence_ids)
        required = set(self.case.ground_truth.required_supporting_evidence_ids)
        return len(predicted & required)

    @property
    def citation_precision(self) -> float | None:
        """Score citations only when the normalized diagnosis is correct."""
        if not self.root_cause_correct:
            return None
        predicted_count = len(set(self.cited_evidence_ids))
        if predicted_count == 0:
            return None
        return self.acceptable_citation_count / predicted_count

    @property
    def citation_recall(self) -> float | None:
        """Score required citations only when the diagnosis is correct."""
        if not self.root_cause_correct:
            return None
        required_count = len(
            set(self.case.ground_truth.required_supporting_evidence_ids)
        )
        if required_count == 0:
            return None
        return self.required_citation_count / required_count

    @property
    def unsupported_citation_ids(self) -> list[str]:
        """Return cited IDs that were not available to this investigation."""
        available_evidence = inspect_logs(self.case.context) + inspect_deployments(
            self.case.context
        )
        available_ids = {item.id for item in available_evidence}
        return [
            evidence_id
            for evidence_id in dict.fromkeys(self.cited_evidence_ids)
            if evidence_id not in available_ids
        ]


@dataclass(frozen=True)
class MetricScore:
    """Keep an aggregate metric numerator and denominator visible."""

    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        """Return the ratio, or None when the metric has no denominator."""
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator


@dataclass(frozen=True)
class InvestigationMetrics:
    """Group the four deterministic initial investigation metrics."""

    status_accuracy: MetricScore
    root_cause_accuracy: MetricScore
    evidence_citation_precision: MetricScore
    evidence_citation_recall: MetricScore


def load_cases(path: Path) -> list[InvestigationBenchmarkCase]:
    """Load the JSON benchmark and validate cross-case identity uniqueness."""
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = [InvestigationBenchmarkCase.model_validate(case) for case in raw_cases]

    case_ids = [case.id for case in cases]
    incident_ids = [case.context.incident.id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("benchmark case IDs must be unique")
    if len(set(incident_ids)) != len(incident_ids):
        raise ValueError("benchmark incident IDs must be unique")

    return cases


def load_benchmark_slice(benchmark: BenchmarkSlice) -> list[InvestigationBenchmarkCase]:
    """Select the frozen core, retrieval-dependent extension, or both."""
    if benchmark == "core":
        return load_cases(CORE_CASES_PATH)
    if benchmark == "retrieval-dependent":
        return load_cases(RETRIEVAL_DEPENDENT_CASES_PATH)

    core_cases = load_cases(CORE_CASES_PATH)
    retrieval_cases = load_cases(RETRIEVAL_DEPENDENT_CASES_PATH)
    combined_cases = core_cases + retrieval_cases

    case_ids = [case.id for case in combined_cases]
    incident_ids = [case.context.incident.id for case in combined_cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("combined benchmark case IDs must be unique")
    if len(set(incident_ids)) != len(incident_ids):
        raise ValueError("combined benchmark incident IDs must be unique")

    return combined_cases


def normalized_root_cause(
    result: InvestigationResult,
) -> RootCauseLabel | None:
    """Read the normalized label carried by structured diagnosis output."""
    if result.diagnosis is None:
        return None
    return result.diagnosis.root_cause_label


def classify_completed_result(
    case: InvestigationBenchmarkCase,
    result: InvestigationResult,
    predicted_root_cause_label: RootCauseLabel | None,
) -> CaseOutcome:
    """Classify a structured result using only deterministic ground truth."""
    truth = case.ground_truth

    if result.status == InvestigationStatus.INCONCLUSIVE:
        if truth.expected_status == InvestigationStatus.INCONCLUSIVE:
            return CaseOutcome.CORRECT_INCONCLUSIVE
        return CaseOutcome.INCORRECT_ANSWER

    if truth.expected_status == InvestigationStatus.INCONCLUSIVE:
        return CaseOutcome.INCORRECT_ANSWER

    if result.diagnosis is None:
        return CaseOutcome.INCORRECT_ANSWER

    predicted_citations = set(result.diagnosis.supporting_evidence_ids)
    required_citations = set(truth.required_supporting_evidence_ids)
    acceptable_citations = set(truth.acceptable_supporting_evidence_ids)
    available_evidence = inspect_logs(case.context) + inspect_deployments(case.context)
    available_citations = {item.id for item in available_evidence}
    # Prohibited labels describe useful competing diagnoses in the benchmark;
    # selecting one is still an ordinary incorrect answer, not a grounding error.
    if predicted_root_cause_label != truth.root_cause_label:
        return CaseOutcome.INCORRECT_ANSWER

    if not predicted_citations <= available_citations:
        return CaseOutcome.UNSUPPORTED_ANSWER

    if not required_citations <= predicted_citations:
        return CaseOutcome.INCORRECT_ANSWER

    if not predicted_citations <= acceptable_citations:
        return CaseOutcome.CORRECT_WITH_EXTRANEOUS_EVIDENCE

    return CaseOutcome.CORRECT_ANSWER


def evaluate_cases(
    database_url: str,
    cases: list[InvestigationBenchmarkCase],
    hypothesis_generator: HypothesisGenerator = generate_fake_hypothesis,
    runbooks_enabled: bool = True,
) -> list[InvestigationCaseResult]:
    """Run every case with retrieved knowledge either supplied or withheld."""
    results: list[InvestigationCaseResult] = []

    for case in cases:
        generated_hypothesis: Hypothesis | None = None

        def generate_and_record(
            incident: Incident,
            evidence: list[Evidence],
            retrieved_runbooks: list[RetrievedRunbook],
        ) -> Hypothesis:
            nonlocal generated_hypothesis
            reasoner_runbooks = retrieved_runbooks if runbooks_enabled else []
            generated_hypothesis = hypothesis_generator(
                incident,
                evidence,
                reasoner_runbooks,
            )
            return generated_hypothesis

        try:
            investigation_result = investigate_incident(
                case.context.model_copy(deep=True),
                database_url=database_url,
                hypothesis_generator=generate_and_record,
            )
        except UnknownEvidenceError as error:
            if generated_hypothesis is None:
                results.append(
                    InvestigationCaseResult(
                        case=case,
                        actual_status=None,
                        predicted_root_cause_label=None,
                        cited_evidence_ids=[],
                        outcome=CaseOutcome.SYSTEM_FAILURE,
                        error=f"{type(error).__name__}: {error}",
                    )
                )
                continue

            results.append(
                InvestigationCaseResult(
                    case=case,
                    actual_status=InvestigationStatus.DIAGNOSED,
                    predicted_root_cause_label=generated_hypothesis.root_cause_label,
                    cited_evidence_ids=list(generated_hypothesis.cited_evidence_ids),
                    outcome=(
                        CaseOutcome.UNSUPPORTED_ANSWER
                        if case.ground_truth.expected_status
                        == InvestigationStatus.DIAGNOSED
                        and generated_hypothesis.root_cause_label
                        == case.ground_truth.root_cause_label
                        else CaseOutcome.INCORRECT_ANSWER
                    ),
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue
        except Exception as error:  # noqa: BLE001 - evaluation must retain all cases
            results.append(
                InvestigationCaseResult(
                    case=case,
                    actual_status=None,
                    predicted_root_cause_label=None,
                    cited_evidence_ids=[],
                    outcome=CaseOutcome.SYSTEM_FAILURE,
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue

        predicted_label = normalized_root_cause(investigation_result)
        cited_evidence_ids = (
            list(investigation_result.diagnosis.supporting_evidence_ids)
            if investigation_result.diagnosis is not None
            else []
        )
        results.append(
            InvestigationCaseResult(
                case=case,
                actual_status=investigation_result.status,
                predicted_root_cause_label=predicted_label,
                cited_evidence_ids=cited_evidence_ids,
                outcome=classify_completed_result(
                    case,
                    investigation_result,
                    predicted_label,
                ),
            )
        )

    return results


def calculate_metrics(
    results: list[InvestigationCaseResult],
) -> InvestigationMetrics:
    """Calculate status, root-cause, and micro-averaged citation metrics."""
    if not results:
        raise ValueError("investigation metrics require at least one case result")

    diagnosed_results = [
        result
        for result in results
        if result.case.ground_truth.expected_status == InvestigationStatus.DIAGNOSED
    ]
    correctly_diagnosed_results = [
        result for result in results if result.root_cause_correct
    ]
    predicted_citation_count = sum(
        len(set(result.cited_evidence_ids)) for result in correctly_diagnosed_results
    )
    required_citation_count = sum(
        len(set(result.case.ground_truth.required_supporting_evidence_ids))
        for result in correctly_diagnosed_results
    )

    return InvestigationMetrics(
        status_accuracy=MetricScore(
            numerator=sum(result.status_correct for result in results),
            denominator=len(results),
        ),
        root_cause_accuracy=MetricScore(
            numerator=sum(result.root_cause_correct for result in diagnosed_results),
            denominator=len(diagnosed_results),
        ),
        evidence_citation_precision=MetricScore(
            numerator=sum(
                result.acceptable_citation_count
                for result in correctly_diagnosed_results
            ),
            denominator=predicted_citation_count,
        ),
        evidence_citation_recall=MetricScore(
            numerator=sum(
                result.required_citation_count for result in correctly_diagnosed_results
            ),
            denominator=required_citation_count,
        ),
    )


def _format_optional_ratio(value: float | None) -> str:
    """Format a per-case metric without treating no denominator as perfect."""
    if value is None:
        return "N/A"
    return f"{value:.0%}"


def _format_metric(score: MetricScore) -> str:
    """Display both counts and the aggregate ratio."""
    if score.value is None:
        return f"{score.numerator}/{score.denominator} (N/A)"
    return f"{score.numerator}/{score.denominator} ({score.value:.0%})"


def print_report(
    results: list[InvestigationCaseResult],
    reasoner_name: str,
    model_name: str,
    runbooks_enabled: bool,
) -> None:
    """Print complete case outcomes before the four aggregate metrics."""
    print(f"Reasoner: {reasoner_name}")
    print(f"Model: {model_name}")
    print(f"Runbooks: {'enabled' if runbooks_enabled else 'disabled'}")
    print()

    for result in results:
        truth = result.case.ground_truth
        actual_status = result.actual_status or "no result"
        expected_label = truth.root_cause_label or "none"
        predicted_label = result.predicted_root_cause_label or "none"
        cited = ", ".join(result.cited_evidence_ids) or "none"
        required = ", ".join(truth.required_supporting_evidence_ids) or "none"
        acceptable = ", ".join(truth.acceptable_supporting_evidence_ids) or "none"
        unsupported = ", ".join(result.unsupported_citation_ids) or "none"

        print(
            f"{result.case.id}: {result.outcome} | "
            f"status={actual_status} expected_status={truth.expected_status} | "
            f"root_cause={predicted_label} expected_root_cause={expected_label}"
        )
        print(
            f"  citations={cited} | required={required} | "
            f"acceptable={acceptable} | precision="
            f"{_format_optional_ratio(result.citation_precision)} | "
            f"recall={_format_optional_ratio(result.citation_recall)} | "
            f"unsupported_citations={unsupported}"
        )
        if result.error is not None:
            print(f"  error={result.error}")

    metrics = calculate_metrics(results)
    print()
    print(f"Status accuracy: {_format_metric(metrics.status_accuracy)}")
    print(f"Root-cause accuracy: {_format_metric(metrics.root_cause_accuracy)}")
    print(
        "Evidence citation precision: "
        f"{_format_metric(metrics.evidence_citation_precision)}"
    )
    print(
        f"Evidence citation recall: {_format_metric(metrics.evidence_citation_recall)}"
    )
    print(
        "Unsupported answers: "
        f"{sum(result.outcome == CaseOutcome.UNSUPPORTED_ANSWER for result in results)}"
    )
    print(
        "Unsupported citations: "
        f"{sum(len(result.unsupported_citation_ids) for result in results)}"
    )
    print(
        "System failures: "
        f"{sum(result.outcome == CaseOutcome.SYSTEM_FAILURE for result in results)}"
    )


def main() -> None:
    """Parse inputs and run the frozen investigation benchmark."""
    parser = argparse.ArgumentParser(
        description="Evaluate end-to-end incident investigations."
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="PostgreSQL connection URL containing populated runbook embeddings.",
    )
    parser.add_argument(
        "--reasoner",
        choices=("fake", "openai", "openrouter"),
        default="fake",
        help="Concrete hypothesis generator to evaluate (default: fake).",
    )
    parser.add_argument(
        "--runbooks",
        choices=("enabled", "disabled"),
        default="enabled",
        help="Supply retrieved runbooks to the reasoner (default: enabled).",
    )
    parser.add_argument(
        "--benchmark",
        choices=("core", "retrieval-dependent", "combined"),
        default="core",
        help="Frozen investigation slice to evaluate (default: core).",
    )
    args = parser.parse_args()

    cases = load_benchmark_slice(args.benchmark)
    if args.reasoner == "openai":
        from resolve_ai.openai_model import (
            OPENAI_REASONING_MODEL,
            generate_openai_hypothesis,
        )

        hypothesis_generator = generate_openai_hypothesis
        model_name = OPENAI_REASONING_MODEL
    elif args.reasoner == "openrouter":
        from resolve_ai.openrouter_model import (
            OPENROUTER_REASONING_MODEL,
            generate_openrouter_hypothesis,
        )

        hypothesis_generator = generate_openrouter_hypothesis
        model_name = OPENROUTER_REASONING_MODEL
    else:
        hypothesis_generator = generate_fake_hypothesis
        model_name = "deterministic-evidence-rules"

    results = evaluate_cases(
        args.database_url,
        cases,
        hypothesis_generator=hypothesis_generator,
        runbooks_enabled=args.runbooks == "enabled",
    )
    print(f"Benchmark: {args.benchmark}")
    print_report(
        results,
        reasoner_name=args.reasoner,
        model_name=model_name,
        runbooks_enabled=args.runbooks == "enabled",
    )


if __name__ == "__main__":
    main()
