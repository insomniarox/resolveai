"""Run the opt-in live-provider check for the Phase 7.2 runtime boundary."""

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator

from resolve_ai.investigation import investigate_evidence
from resolve_ai.models import InvestigationStatus, ReasonerMetadata, RootCauseName
from resolve_ai.reasoning import HypothesisGenerator
from resolve_ai.runtime_input import RuntimeIncidentBundle
from resolve_ai.runtime_reasoner import RUNTIME_PROVIDER_ENV, get_runtime_reasoner

CASES_PATH = Path(__file__).with_name("runtime_reasoning_cases.json")


class RuntimeReasoningCase(BaseModel):
    """Pair one bounded runtime bundle with an exact structural expectation."""

    id: str
    bundle: RuntimeIncidentBundle
    expected_status: InvestigationStatus
    expected_root_cause_label: RootCauseName | None

    @model_validator(mode="after")
    def validate_expectation(self) -> Self:
        diagnosed = self.expected_status == InvestigationStatus.DIAGNOSED
        if diagnosed != (self.expected_root_cause_label is not None):
            raise ValueError("diagnosed cases require exactly one expected label")
        return self


@dataclass(frozen=True)
class RuntimeReasoningResult:
    """Retain one repeat's outcome without hiding provider failures."""

    case_id: str
    repeat: int
    passed: bool
    actual_status: str
    actual_label: str | None
    error: str | None = None


def load_cases(path: Path = CASES_PATH) -> list[RuntimeReasoningCase]:
    """Load and validate the small mutable runtime evaluation set."""
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    return [RuntimeReasoningCase.model_validate(item) for item in raw_cases]


def evaluate_runtime_cases(
    *,
    database_url: str,
    cases: list[RuntimeReasoningCase],
    hypothesis_generator: HypothesisGenerator,
    reasoner: ReasonerMetadata,
    repeats: int,
) -> list[RuntimeReasoningResult]:
    """Run repeated live checks while preserving every failure in the report."""
    results: list[RuntimeReasoningResult] = []
    for repeat in range(1, repeats + 1):
        for case in cases:
            incident, evidence = case.bundle.to_domain()
            try:
                investigation = investigate_evidence(
                    incident=incident,
                    evidence=evidence,
                    database_url=database_url,
                    hypothesis_generator=hypothesis_generator,
                    reasoner=reasoner,
                )
            except Exception as error:  # noqa: BLE001 - retain every eval failure
                results.append(
                    RuntimeReasoningResult(
                        case_id=case.id,
                        repeat=repeat,
                        passed=False,
                        actual_status="system_failure",
                        actual_label=None,
                        error=f"{type(error).__name__}: {error}",
                    )
                )
                continue

            actual_label = (
                investigation.diagnosis.root_cause_label
                if investigation.diagnosis is not None
                else None
            )
            passed = (
                investigation.status == case.expected_status
                and actual_label == case.expected_root_cause_label
            )
            results.append(
                RuntimeReasoningResult(
                    case_id=case.id,
                    repeat=repeat,
                    passed=passed,
                    actual_status=investigation.status.value,
                    actual_label=actual_label,
                )
            )
    return results


def main() -> None:
    """Run a deliberately manual, spend-bearing provider evaluation."""
    parser = argparse.ArgumentParser(
        description="Evaluate the configured live runtime reasoner."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--provider", choices=("openrouter", "openai"))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 10:
        parser.error("--repeats must be between 1 and 10")
    if args.provider:
        os.environ[RUNTIME_PROVIDER_ENV] = args.provider

    configured = get_runtime_reasoner()
    results = evaluate_runtime_cases(
        database_url=args.database_url,
        cases=load_cases(),
        hypothesis_generator=configured.generate,
        reasoner=configured.metadata,
        repeats=args.repeats,
    )
    for result in results:
        label = result.actual_label or "none"
        outcome = "PASS" if result.passed else "FAIL"
        print(
            f"{outcome} repeat={result.repeat} case={result.case_id} "
            f"status={result.actual_status} label={label}"
        )
        if result.error:
            print(f"  error={result.error}")

    passed = sum(result.passed for result in results)
    print(f"Passed: {passed}/{len(results)}")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
