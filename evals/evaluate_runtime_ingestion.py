"""Evaluate the frozen Phase 7.4 runtime-ingestion slice.

The deterministic layer exercises validation, PostgreSQL scope isolation,
cleanup, semantic ranking, and frozen-corpus stability. The optional live layer
reuses the same cases for spend-bearing runtime reasoning measurements. Model
quality misses are reported rather than turned into regression-test failures.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self
from uuid import UUID, uuid4

import psycopg
from pydantic import BaseModel, ValidationError, model_validator

from evals.evaluate_lexical_retrieval import load_cases as load_retrieval_cases
from resolve_ai.investigation import (
    UnknownEvidenceError,
    build_runbook_query,
    investigate_evidence,
)
from resolve_ai.models import (
    Evidence,
    Hypothesis,
    Incident,
    InvestigationResult,
    InvestigationStatus,
    ReasonerMetadata,
    RetrievedKnowledgeDocument,
    RetrievedReferenceKnowledge,
)
from resolve_ai.reasoning import HypothesisGenerator
from resolve_ai.retrieval import (
    count_runbooks_without_embeddings,
    delete_runtime_knowledge_scope,
    semantic_search_runbooks,
    semantic_search_runtime_knowledge_documents,
    store_runtime_knowledge_documents,
)
from resolve_ai.runtime_input import (
    MAX_RUNTIME_KNOWLEDGE_DOCUMENT_CHARACTERS,
    MAX_RUNTIME_KNOWLEDGE_TOTAL_CHARACTERS,
    RuntimeIncidentBundle,
)
from resolve_ai.runtime_reasoner import RUNTIME_PROVIDER_ENV, get_runtime_reasoner

PROJECT_ROOT = Path(__file__).parents[1]
CASES_PATH = Path(__file__).with_name("runtime_ingestion_cases.json")
RUNBOOK_RETRIEVAL_CASES_PATH = Path(__file__).with_name("runbook_retrieval_cases.json")
RUNTIME_KNOWLEDGE_LIMIT = 3
RUNTIME_SCOPE_RETENTION = timedelta(minutes=15)

RUNTIME_INGESTION_CASES_SHA256 = (
    "71d41e1ad01af844ab5e0a83cbabb8d6681a1de409b0691e4b248a3363a19245"
)
LEGACY_ARTIFACT_SHA256 = {
    "investigation_cases.json": (
        "df204565818e30b02f330f65bc47a1756b77d13ffd234ad62dbd95d4fedd4871"
    ),
    "investigation_retrieval_cases.json": (
        "37eb1117be695d6066a334766e8a1b28458b6b59cba12a818fa218e4737e79bd"
    ),
    "runbook_retrieval_cases.json": (
        "5327add74821f0a19c49b8082025c482dade11a681d788fbda7009abaa6d5dee"
    ),
    "runtime_reasoning_cases.json": (
        "8fdd249f073b643fe9240b6106f3eeee0485d8c4217ee56be3acd00afeab30ee"
    ),
}


class RequiredKnowledgeDocument(BaseModel):
    """Describe how highly one relevant runtime document must rank."""

    document_id: str
    max_rank: Literal[1, 3]


class RuntimeIngestionGroundTruth(BaseModel):
    """Keep retrieval, reasoning, and citation expectations together."""

    expected_status: InvestigationStatus
    expected_root_cause_label: str | None
    required_supporting_evidence_ids: list[str]
    acceptable_supporting_evidence_ids: list[str]
    required_knowledge_documents: list[RequiredKnowledgeDocument]
    distractor_document_ids: list[str]
    expected_inconclusive_reason: str | None

    @model_validator(mode="after")
    def validate_ground_truth(self) -> Self:
        """Reject ambiguous diagnosed/inconclusive or citation expectations."""
        required = set(self.required_supporting_evidence_ids)
        acceptable = set(self.acceptable_supporting_evidence_ids)
        required_documents = [
            item.document_id for item in self.required_knowledge_documents
        ]

        if len(required) != len(self.required_supporting_evidence_ids):
            raise ValueError("required Evidence IDs must be unique")
        if len(acceptable) != len(self.acceptable_supporting_evidence_ids):
            raise ValueError("acceptable Evidence IDs must be unique")
        if not required <= acceptable:
            raise ValueError("required Evidence must also be acceptable")
        if len(required_documents) != len(set(required_documents)):
            raise ValueError("required runtime document IDs must be unique")
        if len(self.distractor_document_ids) != len(set(self.distractor_document_ids)):
            raise ValueError("distractor runtime document IDs must be unique")

        diagnosed = self.expected_status == InvestigationStatus.DIAGNOSED
        if diagnosed:
            if self.expected_root_cause_label is None or not required:
                raise ValueError(
                    "diagnosed cases require a label and supporting Evidence"
                )
            if self.expected_inconclusive_reason is not None:
                raise ValueError("diagnosed cases cannot have an inconclusive reason")
        else:
            if self.expected_root_cause_label is not None or required or acceptable:
                raise ValueError(
                    "inconclusive cases cannot have a label or citation expectations"
                )
            if not self.expected_inconclusive_reason:
                raise ValueError("inconclusive cases require an expected reason")
        return self


class RuntimeIngestionCase(BaseModel):
    """Pair one valid runtime bundle with independently labeled truth."""

    id: str
    bundle: RuntimeIncidentBundle
    ground_truth: RuntimeIngestionGroundTruth

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Require every labeled identifier to exist in this case's bundle."""
        evidence_ids = {item.id for item in self.bundle.evidence}
        document_ids = {item.id for item in self.bundle.knowledge_documents}
        truth = self.ground_truth
        labeled_evidence = set(truth.acceptable_supporting_evidence_ids)
        required_documents = {
            item.document_id for item in truth.required_knowledge_documents
        }
        distractors = set(truth.distractor_document_ids)

        if not labeled_evidence <= evidence_ids:
            unknown = sorted(labeled_evidence - evidence_ids)
            raise ValueError(f"ground truth references unknown Evidence: {unknown}")
        if required_documents & distractors:
            raise ValueError("a runtime document cannot be required and a distractor")
        if required_documents | distractors != document_ids:
            raise ValueError(
                "every runtime document must be labeled required or distractor"
            )
        return self


class MalformedBundleMutation(StrEnum):
    """List the five explicit invalid-input pressures in the frozen suite."""

    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    DUPLICATE_DOCUMENT_ID = "duplicate_document_id"
    EVIDENCE_DOCUMENT_ID_COLLISION = "evidence_document_id_collision"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    AGGREGATE_CONTENT_TOO_LARGE = "aggregate_content_too_large"


class MalformedRuntimeBundleCase(BaseModel):
    """Build a reviewable invalid bundle from one frozen valid input."""

    id: str
    base_case_id: str
    mutation: MalformedBundleMutation
    expected_error_contains: str


class ScopeIsolationCase(BaseModel):
    """Identify the two valid bundles held concurrently in PostgreSQL."""

    id: str
    first_case_id: str
    second_case_id: str


class RuntimeIngestionDataset(BaseModel):
    """Represent the complete, separately frozen Phase 7.4 dataset."""

    valid_cases: list[RuntimeIngestionCase]
    malformed_cases: list[MalformedRuntimeBundleCase]
    scope_isolation_case: ScopeIsolationCase

    @model_validator(mode="after")
    def validate_dataset_invariants(self) -> Self:
        """Keep every identity unique and every cross-reference resolvable."""
        if len(self.valid_cases) != 5 or len(self.malformed_cases) != 5:
            raise ValueError(
                "runtime ingestion requires five valid and five malformed cases"
            )

        groups = {
            "valid case": [case.id for case in self.valid_cases],
            "malformed case": [case.id for case in self.malformed_cases],
            "incident": [case.bundle.incident.id for case in self.valid_cases],
            "Evidence": [
                item.id for case in self.valid_cases for item in case.bundle.evidence
            ],
            "runtime document": [
                item.id
                for case in self.valid_cases
                for item in case.bundle.knowledge_documents
            ],
        }
        for name, identifiers in groups.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{name} IDs must be unique across the dataset")

        case_ids = set(groups["valid case"])
        for malformed_case in self.malformed_cases:
            if malformed_case.base_case_id not in case_ids:
                raise ValueError("malformed case references an unknown valid case")
        isolation_ids = {
            self.scope_isolation_case.first_case_id,
            self.scope_isolation_case.second_case_id,
        }
        if len(isolation_ids) != 2 or not isolation_ids <= case_ids:
            raise ValueError("scope isolation must reference two distinct valid cases")
        return self

    def case_by_id(self, case_id: str) -> RuntimeIngestionCase:
        """Return one validated case for a dataset-owned cross-reference."""
        return next(case for case in self.valid_cases if case.id == case_id)


@dataclass(frozen=True)
class MetricScore:
    """Keep every aggregate numerator and denominator visible."""

    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        """Return the ratio unless the metric has no applicable cases."""
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator


@dataclass(frozen=True)
class RuntimeRetrievalResult:
    """Record one deterministic scoped retrieval and its cleanup outcome."""

    case: RuntimeIngestionCase
    retrieved_document_ids: list[str]
    similarity_scores: list[float]
    retained_scope_rows: int
    error: str | None = None


@dataclass(frozen=True)
class MalformedBundleResult:
    """Record whether one raw invalid bundle was rejected by Pydantic."""

    case_id: str
    rejected: bool
    expected_error_found: bool
    error: str | None


@dataclass(frozen=True)
class ScopeIsolationResult:
    """Record cross-scope visibility and cleanup while both scopes coexist."""

    case_id: str
    first_retrieved_document_ids: list[str]
    second_retrieved_document_ids: list[str]
    leaked_document_ids: list[str]
    retained_scope_rows: int
    error: str | None = None


@dataclass(frozen=True)
class DeterministicEvaluationReport:
    """Group Phase 7.4's deterministic measurements and safety gates."""

    retrieval_results: list[RuntimeRetrievalResult]
    malformed_results: list[MalformedBundleResult]
    scope_isolation: ScopeIsolationResult
    frozen_runbooks_before: dict[str, list[str]]
    frozen_runbooks_after: dict[str, list[str]]

    @property
    def runtime_document_top1_accuracy(self) -> MetricScore:
        """Score requirements explicitly labeled as Top-1 expectations."""
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
        """Measure every required document against the returned Top-3."""
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
    def malformed_rejection_rate(self) -> MetricScore:
        """Count invalid bundles rejected with the expected validation boundary."""
        return MetricScore(
            numerator=sum(
                result.rejected and result.expected_error_found
                for result in self.malformed_results
            ),
            denominator=len(self.malformed_results),
        )

    @property
    def retained_row_count(self) -> int:
        """Count evaluation-owned rows left after every deterministic operation."""
        return (
            sum(result.retained_scope_rows for result in self.retrieval_results)
            + self.scope_isolation.retained_scope_rows
        )

    @property
    def safety_gates_pass(self) -> bool:
        """Enforce deterministic boundaries without requiring perfect ranking."""
        rejection = self.malformed_rejection_rate
        return (
            rejection.numerator == rejection.denominator
            and not self.scope_isolation.leaked_document_ids
            and self.retained_row_count == 0
            and self.frozen_runbooks_before == self.frozen_runbooks_after
            and not any(result.error for result in self.retrieval_results)
            and self.scope_isolation.error is None
        )


class ReasoningOutcome(StrEnum):
    """Separate answer quality, unsupported output, and execution failures."""

    CORRECT_ANSWER = "correct_answer"
    CORRECT_WITH_EXTRANEOUS_EVIDENCE = "correct_with_extraneous_evidence"
    CORRECT_INCONCLUSIVE = "correct_inconclusive"
    INCORRECT_ANSWER = "incorrect_answer"
    UNSUPPORTED_ANSWER = "unsupported_answer"
    SYSTEM_FAILURE = "system_failure"


@dataclass(frozen=True)
class RuntimeReasoningResult:
    """Retain one live repeat, including attempted pre-verification citations."""

    case: RuntimeIngestionCase
    repeat: int
    provider: str
    model: str
    actual_status: InvestigationStatus | None
    predicted_root_cause_label: str | None
    attempted_citation_ids: list[str]
    accepted_citation_ids: list[str]
    retrieved_document_ids: list[str]
    outcome: ReasoningOutcome
    retained_scope_rows: int
    probable_root_cause: str | None = None
    recommended_remediation: str | None = None
    error: str | None = None

    @property
    def status_correct(self) -> bool:
        """Return whether the accepted result has the expected status."""
        return self.actual_status == self.case.ground_truth.expected_status

    @property
    def root_cause_correct(self) -> bool:
        """Return whether an accepted diagnosis has the expected label."""
        return (
            self.actual_status == InvestigationStatus.DIAGNOSED
            and self.case.ground_truth.expected_status == InvestigationStatus.DIAGNOSED
            and self.predicted_root_cause_label
            == self.case.ground_truth.expected_root_cause_label
        )

    @property
    def unsupported_attempted_citation_ids(self) -> list[str]:
        """Return attempted citations outside the submitted Evidence set."""
        evidence_ids = {item.id for item in self.case.bundle.evidence}
        return [
            item_id
            for item_id in dict.fromkeys(self.attempted_citation_ids)
            if item_id not in evidence_ids
        ]

    @property
    def attempted_knowledge_document_citation_ids(self) -> list[str]:
        """Return attempted citations that name untrusted runtime documents."""
        document_ids = {item.id for item in self.case.bundle.knowledge_documents}
        return [
            item_id
            for item_id in dict.fromkeys(self.attempted_citation_ids)
            if item_id in document_ids
        ]

    @property
    def accepted_unsupported_citation_ids(self) -> list[str]:
        """Return any out-of-boundary citation that reached a final diagnosis."""
        evidence_ids = {item.id for item in self.case.bundle.evidence}
        return [
            item_id
            for item_id in dict.fromkeys(self.accepted_citation_ids)
            if item_id not in evidence_ids
        ]


@dataclass(frozen=True)
class RuntimeReasoningMetrics:
    """Group aggregate live-provider measurements."""

    status_accuracy: MetricScore
    root_cause_accuracy: MetricScore
    evidence_citation_precision: MetricScore
    evidence_citation_recall: MetricScore
    correct_abstention_rate: MetricScore
    repeat_agreement: MetricScore
    unsupported_citation_count: int
    attempted_knowledge_document_citation_count: int
    accepted_unsupported_citation_count: int
    system_failure_count: int
    retained_row_count: int


def _sha256(path: Path) -> str:
    """Return the byte-level digest used by frozen-artifact guards."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_artifact_hashes() -> None:
    """Fail before evaluation if the new or legacy datasets changed silently."""
    if _sha256(CASES_PATH) != RUNTIME_INGESTION_CASES_SHA256:
        raise RuntimeError("runtime ingestion dataset hash does not match")
    for filename, expected_digest in LEGACY_ARTIFACT_SHA256.items():
        artifact_path = Path(__file__).with_name(filename)
        if _sha256(artifact_path) != expected_digest:
            raise RuntimeError(f"legacy evaluation artifact changed: {filename}")


def load_dataset(path: Path = CASES_PATH) -> RuntimeIngestionDataset:
    """Load the frozen runtime suite and validate every cross-case invariant."""
    raw_dataset = json.loads(path.read_text(encoding="utf-8"))
    dataset = RuntimeIngestionDataset.model_validate(raw_dataset)
    _validate_malformed_case_coverage(dataset.malformed_cases)
    return dataset


def _validate_malformed_case_coverage(
    cases: list[MalformedRuntimeBundleCase],
) -> None:
    """Require exactly one frozen case for every planned invalid pressure."""
    mutations = [case.mutation for case in cases]
    if Counter(mutations) != Counter(MalformedBundleMutation):
        raise ValueError("malformed cases must cover every mutation exactly once")


def build_malformed_bundle(
    dataset: RuntimeIngestionDataset,
    malformed_case: MalformedRuntimeBundleCase,
) -> dict:
    """Materialize one invalid raw bundle without storing a 20 kB filler string."""
    base_case = dataset.case_by_id(malformed_case.base_case_id)
    raw_bundle = deepcopy(base_case.bundle.model_dump(mode="json"))
    documents = raw_bundle["knowledge_documents"]

    if malformed_case.mutation == MalformedBundleMutation.UNSUPPORTED_SCHEMA_VERSION:
        raw_bundle["schema_version"] = 2
    elif malformed_case.mutation == MalformedBundleMutation.DUPLICATE_DOCUMENT_ID:
        documents[1]["id"] = documents[0]["id"]
    elif (
        malformed_case.mutation
        == MalformedBundleMutation.EVIDENCE_DOCUMENT_ID_COLLISION
    ):
        documents[0]["id"] = raw_bundle["evidence"][0]["id"]
    elif malformed_case.mutation == MalformedBundleMutation.UNSUPPORTED_CONTENT_TYPE:
        documents[0]["content_type"] = "application/pdf"
    else:
        per_document_limit = MAX_RUNTIME_KNOWLEDGE_DOCUMENT_CHARACTERS
        documents[0]["content"] = "a" * per_document_limit
        documents[1]["content"] = "b" * per_document_limit
        remaining = MAX_RUNTIME_KNOWLEDGE_TOTAL_CHARACTERS - 2 * per_document_limit
        documents[2]["content"] = "c" * (remaining + 1)
    return raw_bundle


def evaluate_malformed_bundles(
    dataset: RuntimeIngestionDataset,
) -> list[MalformedBundleResult]:
    """Validate invalid raw input without exposing storage or reasoner callbacks."""
    results: list[MalformedBundleResult] = []
    for malformed_case in dataset.malformed_cases:
        raw_bundle = build_malformed_bundle(dataset, malformed_case)
        try:
            RuntimeIncidentBundle.model_validate(raw_bundle)
        except ValidationError as error:
            message = str(error)
            results.append(
                MalformedBundleResult(
                    case_id=malformed_case.id,
                    rejected=True,
                    expected_error_found=(
                        malformed_case.expected_error_contains in message
                    ),
                    error=message,
                )
            )
        else:
            results.append(
                MalformedBundleResult(
                    case_id=malformed_case.id,
                    rejected=False,
                    expected_error_found=False,
                    error=None,
                )
            )
    return results


def _count_runtime_scope_rows(database_url: str, scope_id: UUID) -> int:
    """Count only rows owned by one evaluation-created scope."""
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT count(*)
            FROM runtime_knowledge_documents
            WHERE scope_id = %s
            """,
            (scope_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("runtime scope count returned no row")
    return int(row[0])


def _case_query(case: RuntimeIngestionCase) -> str:
    """Build the exact deterministic query used by the application workflow."""
    incident, evidence, _ = case.bundle.to_domain()
    return build_runbook_query(incident, evidence)


def evaluate_runtime_retrieval_case(
    database_url: str,
    case: RuntimeIngestionCase,
) -> RuntimeRetrievalResult:
    """Store, rank, and clean one valid runtime document set."""
    scope_id = uuid4()
    retrieved_ids: list[str] = []
    similarity_scores: list[float] = []
    error_message: str | None = None
    _, _, documents = case.bundle.to_domain()
    try:
        store_runtime_knowledge_documents(
            database_url=database_url,
            scope_id=scope_id,
            documents=documents,
            expires_at=datetime.now(UTC) + RUNTIME_SCOPE_RETENTION,
        )
        retrieved = semantic_search_runtime_knowledge_documents(
            database_url=database_url,
            scope_id=scope_id,
            query=_case_query(case),
            limit=RUNTIME_KNOWLEDGE_LIMIT,
        )
        retrieved_ids = [item.id for item in retrieved]
        similarity_scores = [item.similarity_score for item in retrieved]
    except Exception as error:  # noqa: BLE001 - retain evaluation failure
        error_message = f"{type(error).__name__}: {error}"
    finally:
        try:
            delete_runtime_knowledge_scope(database_url, scope_id)
        except Exception as cleanup_error:  # noqa: BLE001 - report cleanup failure
            cleanup_message = f"{type(cleanup_error).__name__}: {cleanup_error}"
            error_message = error_message or cleanup_message

    retained_rows = _count_runtime_scope_rows(database_url, scope_id)
    return RuntimeRetrievalResult(
        case=case,
        retrieved_document_ids=retrieved_ids,
        similarity_scores=similarity_scores,
        retained_scope_rows=retained_rows,
        error=error_message,
    )


def evaluate_scope_isolation(
    database_url: str,
    dataset: RuntimeIngestionDataset,
) -> ScopeIsolationResult:
    """Hold two scopes concurrently and prove neither query sees foreign rows."""
    isolation = dataset.scope_isolation_case
    first_case = dataset.case_by_id(isolation.first_case_id)
    second_case = dataset.case_by_id(isolation.second_case_id)
    first_scope = uuid4()
    second_scope = uuid4()
    first_ids: list[str] = []
    second_ids: list[str] = []
    leaked_ids: list[str] = []
    error_message: str | None = None

    try:
        for scope_id, case in (
            (first_scope, first_case),
            (second_scope, second_case),
        ):
            _, _, documents = case.bundle.to_domain()
            store_runtime_knowledge_documents(
                database_url=database_url,
                scope_id=scope_id,
                documents=documents,
                expires_at=datetime.now(UTC) + RUNTIME_SCOPE_RETENTION,
            )

        first_results = semantic_search_runtime_knowledge_documents(
            database_url,
            first_scope,
            _case_query(first_case),
            RUNTIME_KNOWLEDGE_LIMIT,
        )
        second_results = semantic_search_runtime_knowledge_documents(
            database_url,
            second_scope,
            _case_query(second_case),
            RUNTIME_KNOWLEDGE_LIMIT,
        )
        first_ids = [item.id for item in first_results]
        second_ids = [item.id for item in second_results]
        first_document_ids = {item.id for item in first_case.bundle.knowledge_documents}
        second_document_ids = {
            item.id for item in second_case.bundle.knowledge_documents
        }
        leaked_ids = sorted(
            (set(first_ids) & second_document_ids)
            | (set(second_ids) & first_document_ids)
        )
    except Exception as error:  # noqa: BLE001 - retain evaluation failure
        error_message = f"{type(error).__name__}: {error}"
    finally:
        for scope_id in (first_scope, second_scope):
            try:
                delete_runtime_knowledge_scope(database_url, scope_id)
            except Exception as cleanup_error:  # noqa: BLE001
                cleanup_message = f"{type(cleanup_error).__name__}: {cleanup_error}"
                error_message = error_message or cleanup_message

    retained_rows = sum(
        _count_runtime_scope_rows(database_url, scope_id)
        for scope_id in (first_scope, second_scope)
    )
    return ScopeIsolationResult(
        case_id=isolation.id,
        first_retrieved_document_ids=first_ids,
        second_retrieved_document_ids=second_ids,
        leaked_document_ids=leaked_ids,
        retained_scope_rows=retained_rows,
        error=error_message,
    )


def snapshot_frozen_runbook_results(database_url: str) -> dict[str, list[str]]:
    """Capture ordered Top-3 results for all eighteen frozen retrieval queries."""
    cases = load_retrieval_cases(RUNBOOK_RETRIEVAL_CASES_PATH)
    return {
        case.id: [
            item.id
            for item in semantic_search_runbooks(
                database_url=database_url,
                query=case.query,
                limit=3,
            )
        ]
        for case in cases
    }


def evaluate_deterministic_layer(
    database_url: str,
    dataset: RuntimeIngestionDataset,
) -> DeterministicEvaluationReport:
    """Run ranking and safety checks without invoking any model provider."""
    if count_runbooks_without_embeddings(database_url):
        raise RuntimeError("all frozen runbooks require stored embeddings")

    before = snapshot_frozen_runbook_results(database_url)
    retrieval_results = [
        evaluate_runtime_retrieval_case(database_url, case)
        for case in dataset.valid_cases
    ]
    isolation_result = evaluate_scope_isolation(database_url, dataset)
    malformed_results = evaluate_malformed_bundles(dataset)
    after = snapshot_frozen_runbook_results(database_url)
    return DeterministicEvaluationReport(
        retrieval_results=retrieval_results,
        malformed_results=malformed_results,
        scope_isolation=isolation_result,
        frozen_runbooks_before=before,
        frozen_runbooks_after=after,
    )


def _completed_reasoning_outcome(
    case: RuntimeIngestionCase,
    result: InvestigationResult,
) -> ReasoningOutcome:
    """Classify one accepted structured result against frozen runtime truth."""
    truth = case.ground_truth
    if result.status == InvestigationStatus.INCONCLUSIVE:
        if truth.expected_status == InvestigationStatus.INCONCLUSIVE:
            return ReasoningOutcome.CORRECT_INCONCLUSIVE
        return ReasoningOutcome.INCORRECT_ANSWER
    if truth.expected_status == InvestigationStatus.INCONCLUSIVE:
        return ReasoningOutcome.INCORRECT_ANSWER
    if result.diagnosis is None:
        return ReasoningOutcome.INCORRECT_ANSWER

    predicted = set(result.diagnosis.supporting_evidence_ids)
    required = set(truth.required_supporting_evidence_ids)
    acceptable = set(truth.acceptable_supporting_evidence_ids)
    available = {item.id for item in case.bundle.evidence}
    if result.diagnosis.root_cause_label != truth.expected_root_cause_label:
        return ReasoningOutcome.INCORRECT_ANSWER
    if not predicted <= available:
        return ReasoningOutcome.UNSUPPORTED_ANSWER
    if not required <= predicted:
        return ReasoningOutcome.INCORRECT_ANSWER
    if not predicted <= acceptable:
        return ReasoningOutcome.CORRECT_WITH_EXTRANEOUS_EVIDENCE
    return ReasoningOutcome.CORRECT_ANSWER


def evaluate_runtime_reasoning(
    *,
    database_url: str,
    dataset: RuntimeIngestionDataset,
    hypothesis_generator: HypothesisGenerator,
    reasoner: ReasonerMetadata,
    repeats: int,
) -> list[RuntimeReasoningResult]:
    """Run the frozen Phase 7.4 cases through the shared live evaluation loop."""
    return evaluate_runtime_reasoning_cases(
        database_url=database_url,
        cases=dataset.valid_cases,
        hypothesis_generator=hypothesis_generator,
        reasoner=reasoner,
        repeats=repeats,
    )


def evaluate_runtime_reasoning_cases(
    *,
    database_url: str,
    cases: list[RuntimeIngestionCase],
    hypothesis_generator: HypothesisGenerator,
    reasoner: ReasonerMetadata,
    repeats: int,
) -> list[RuntimeReasoningResult]:
    """Run explicit runtime cases while retaining output, failure, and cleanup."""
    results: list[RuntimeReasoningResult] = []
    for repeat in range(1, repeats + 1):
        for case in cases:
            scope_id = uuid4()
            incident, evidence, documents = case.bundle.to_domain()
            generated_hypothesis: Hypothesis | None = None
            retrieved_document_ids: list[str] = []
            investigation_result: InvestigationResult | None = None
            error_message: str | None = None
            outcome = ReasoningOutcome.SYSTEM_FAILURE

            def generate_and_record(
                current_incident: Incident,
                current_evidence: list[Evidence],
                retrieved_knowledge: list[RetrievedReferenceKnowledge],
            ) -> Hypothesis:
                nonlocal generated_hypothesis, retrieved_document_ids
                retrieved_document_ids = [
                    item.id
                    for item in retrieved_knowledge
                    if isinstance(item, RetrievedKnowledgeDocument)
                ]
                generated_hypothesis = hypothesis_generator(
                    current_incident,
                    current_evidence,
                    retrieved_knowledge,
                )
                return generated_hypothesis

            try:
                store_runtime_knowledge_documents(
                    database_url=database_url,
                    scope_id=scope_id,
                    documents=documents,
                    expires_at=datetime.now(UTC) + RUNTIME_SCOPE_RETENTION,
                )
                investigation_result = investigate_evidence(
                    incident=incident,
                    evidence=evidence,
                    database_url=database_url,
                    hypothesis_generator=generate_and_record,
                    reasoner=reasoner,
                    knowledge_scope_id=scope_id,
                )
                outcome = _completed_reasoning_outcome(case, investigation_result)
            except UnknownEvidenceError as error:
                error_message = f"{type(error).__name__}: {error}"
                attempted = (
                    generated_hypothesis.cited_evidence_ids
                    if generated_hypothesis is not None
                    else []
                )
                available = {item.id for item in case.bundle.evidence}
                if generated_hypothesis is not None and not set(attempted) <= available:
                    outcome = ReasoningOutcome.UNSUPPORTED_ANSWER
                else:
                    outcome = ReasoningOutcome.INCORRECT_ANSWER
            except Exception as error:  # noqa: BLE001 - retain provider failure
                error_message = f"{type(error).__name__}: {error}"
            finally:
                try:
                    delete_runtime_knowledge_scope(database_url, scope_id)
                except Exception as cleanup_error:  # noqa: BLE001
                    cleanup_message = f"{type(cleanup_error).__name__}: {cleanup_error}"
                    error_message = error_message or cleanup_message
                    outcome = ReasoningOutcome.SYSTEM_FAILURE

            retained_rows = _count_runtime_scope_rows(database_url, scope_id)
            diagnosis = (
                investigation_result.diagnosis
                if investigation_result is not None
                else None
            )
            results.append(
                RuntimeReasoningResult(
                    case=case,
                    repeat=repeat,
                    provider=reasoner.provider,
                    model=reasoner.model,
                    actual_status=(
                        investigation_result.status
                        if investigation_result is not None
                        else None
                    ),
                    predicted_root_cause_label=(
                        diagnosis.root_cause_label
                        if diagnosis is not None
                        else (
                            generated_hypothesis.root_cause_label
                            if generated_hypothesis is not None
                            else None
                        )
                    ),
                    attempted_citation_ids=(
                        list(generated_hypothesis.cited_evidence_ids)
                        if generated_hypothesis is not None
                        else []
                    ),
                    accepted_citation_ids=(
                        list(diagnosis.supporting_evidence_ids)
                        if diagnosis is not None
                        else []
                    ),
                    retrieved_document_ids=retrieved_document_ids,
                    outcome=outcome,
                    retained_scope_rows=retained_rows,
                    probable_root_cause=(
                        diagnosis.probable_root_cause
                        if diagnosis is not None
                        else (
                            generated_hypothesis.probable_root_cause
                            if generated_hypothesis is not None
                            else None
                        )
                    ),
                    recommended_remediation=(
                        diagnosis.recommended_remediation
                        if diagnosis is not None
                        else (
                            generated_hypothesis.recommended_remediation
                            if generated_hypothesis is not None
                            else None
                        )
                    ),
                    error=error_message,
                )
            )
    return results


def calculate_reasoning_metrics(
    results: list[RuntimeReasoningResult],
) -> RuntimeReasoningMetrics:
    """Calculate reasoning, citation, abstention, and repeatability metrics."""
    if not results:
        raise ValueError("reasoning metrics require at least one result")

    expected_diagnosed = [
        result
        for result in results
        if result.case.ground_truth.expected_status == InvestigationStatus.DIAGNOSED
    ]
    correctly_diagnosed = [result for result in results if result.root_cause_correct]
    expected_inconclusive = [
        result
        for result in results
        if result.case.ground_truth.expected_status == InvestigationStatus.INCONCLUSIVE
    ]
    predicted_citation_count = sum(
        len(set(result.accepted_citation_ids)) for result in correctly_diagnosed
    )
    required_citation_count = sum(
        len(set(result.case.ground_truth.required_supporting_evidence_ids))
        for result in correctly_diagnosed
    )
    acceptable_citation_count = sum(
        len(
            set(result.accepted_citation_ids)
            & set(result.case.ground_truth.acceptable_supporting_evidence_ids)
        )
        for result in correctly_diagnosed
    )
    supplied_required_citation_count = sum(
        len(
            set(result.accepted_citation_ids)
            & set(result.case.ground_truth.required_supporting_evidence_ids)
        )
        for result in correctly_diagnosed
    )

    results_by_case: dict[str, list[RuntimeReasoningResult]] = {}
    for result in results:
        results_by_case.setdefault(result.case.id, []).append(result)
    agreeing_cases = 0
    for case_results in results_by_case.values():
        signatures = {
            (
                result.actual_status,
                result.predicted_root_cause_label,
            )
            for result in case_results
        }
        agreeing_cases += len(signatures) == 1

    return RuntimeReasoningMetrics(
        status_accuracy=MetricScore(
            numerator=sum(result.status_correct for result in results),
            denominator=len(results),
        ),
        root_cause_accuracy=MetricScore(
            numerator=sum(result.root_cause_correct for result in expected_diagnosed),
            denominator=len(expected_diagnosed),
        ),
        evidence_citation_precision=MetricScore(
            numerator=acceptable_citation_count,
            denominator=predicted_citation_count,
        ),
        evidence_citation_recall=MetricScore(
            numerator=supplied_required_citation_count,
            denominator=required_citation_count,
        ),
        correct_abstention_rate=MetricScore(
            numerator=sum(
                result.outcome == ReasoningOutcome.CORRECT_INCONCLUSIVE
                for result in expected_inconclusive
            ),
            denominator=len(expected_inconclusive),
        ),
        repeat_agreement=MetricScore(
            numerator=agreeing_cases,
            denominator=len(results_by_case),
        ),
        unsupported_citation_count=sum(
            len(result.unsupported_attempted_citation_ids) for result in results
        ),
        attempted_knowledge_document_citation_count=sum(
            len(result.attempted_knowledge_document_citation_ids) for result in results
        ),
        accepted_unsupported_citation_count=sum(
            len(result.accepted_unsupported_citation_ids) for result in results
        ),
        system_failure_count=sum(
            result.outcome == ReasoningOutcome.SYSTEM_FAILURE for result in results
        ),
        retained_row_count=sum(result.retained_scope_rows for result in results),
    )


def _format_metric(metric: MetricScore) -> str:
    """Render counts and ratio without treating no denominator as perfect."""
    if metric.value is None:
        return f"{metric.numerator}/{metric.denominator} (N/A)"
    return f"{metric.numerator}/{metric.denominator} ({metric.value:.0%})"


def print_deterministic_report(report: DeterministicEvaluationReport) -> None:
    """Print case-level retrieval observations before aggregate safety gates."""
    print("Deterministic ingestion and retrieval")
    for result in report.retrieval_results:
        ids = ", ".join(result.retrieved_document_ids) or "none"
        scores = ", ".join(f"{score:.4f}" for score in result.similarity_scores)
        print(
            f"{result.case.id}: documents={ids} scores={scores or 'none'} "
            f"retained_rows={result.retained_scope_rows}"
        )
        if result.error:
            print(f"  error={result.error}")

    isolation = report.scope_isolation
    print(
        f"{isolation.case_id}: leakage={len(isolation.leaked_document_ids)} "
        f"retained_rows={isolation.retained_scope_rows}"
    )
    if isolation.error:
        print(f"  error={isolation.error}")
    print(
        "Runtime-document Top-1 accuracy: "
        f"{_format_metric(report.runtime_document_top1_accuracy)}"
    )
    print(
        "Required-document Top-3 recall: "
        f"{_format_metric(report.required_document_top3_recall)}"
    )
    print(
        f"Malformed-bundle rejection: {_format_metric(report.malformed_rejection_rate)}"
    )
    print("Accidental provider calls for malformed bundles: 0")
    print(f"Cross-scope leakage count: {len(isolation.leaked_document_ids)}")
    print(f"Post-cleanup retained row count: {report.retained_row_count}")
    print(
        "Frozen runbook results unchanged: "
        f"{report.frozen_runbooks_before == report.frozen_runbooks_after}"
    )
    print(
        f"Deterministic safety gates: {'PASS' if report.safety_gates_pass else 'FAIL'}"
    )


def print_reasoning_report(results: list[RuntimeReasoningResult]) -> None:
    """Print every live outcome and aggregate nondeterministic measurements."""
    first = results[0]
    print()
    print(f"Live provider: {first.provider}")
    print(f"Model: {first.model}")
    for result in results:
        status = result.actual_status or "no_result"
        label = result.predicted_root_cause_label or "none"
        citations = ", ".join(result.accepted_citation_ids) or "none"
        attempted = ", ".join(result.attempted_citation_ids) or "none"
        documents = ", ".join(result.retrieved_document_ids) or "none"
        print(
            f"repeat={result.repeat} case={result.case.id} "
            f"outcome={result.outcome} status={status} label={label}"
        )
        print(
            f"  documents={documents} attempted_citations={attempted} "
            f"accepted_citations={citations} retained_rows={result.retained_scope_rows}"
        )
        if result.probable_root_cause:
            print(f"  probable_root_cause={result.probable_root_cause}")
        if result.error:
            print(f"  error={result.error}")

    metrics = calculate_reasoning_metrics(results)
    print(f"Status accuracy: {_format_metric(metrics.status_accuracy)}")
    print(f"Root-cause accuracy: {_format_metric(metrics.root_cause_accuracy)}")
    print(
        "Evidence citation precision: "
        f"{_format_metric(metrics.evidence_citation_precision)}"
    )
    print(
        f"Evidence citation recall: {_format_metric(metrics.evidence_citation_recall)}"
    )
    print(f"Correct-abstention rate: {_format_metric(metrics.correct_abstention_rate)}")
    print(f"Repeat agreement: {_format_metric(metrics.repeat_agreement)}")
    print(f"Unsupported attempted citations: {metrics.unsupported_citation_count}")
    print(
        "Attempted KnowledgeDocument citations: "
        f"{metrics.attempted_knowledge_document_citation_count}"
    )
    print(
        f"Accepted unsupported citations: {metrics.accepted_unsupported_citation_count}"
    )
    print(f"System failures: {metrics.system_failure_count}")
    print(f"Post-cleanup retained row count: {metrics.retained_row_count}")


def main() -> None:
    """Run deterministic gates and optionally the capped live baseline."""
    parser = argparse.ArgumentParser(
        description="Evaluate frozen Phase 7.4 runtime knowledge ingestion."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--live-provider", choices=("openrouter", "openai"))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 10:
        parser.error("--repeats must be between 1 and 10")

    verify_frozen_artifact_hashes()
    dataset = load_dataset()
    deterministic_report = evaluate_deterministic_layer(args.database_url, dataset)
    print_deterministic_report(deterministic_report)
    if not deterministic_report.safety_gates_pass:
        raise SystemExit(1)

    if args.live_provider:
        os.environ[RUNTIME_PROVIDER_ENV] = args.live_provider
        configured = get_runtime_reasoner()
        reasoning_results = evaluate_runtime_reasoning(
            database_url=args.database_url,
            dataset=dataset,
            hypothesis_generator=configured.generate,
            reasoner=configured.metadata,
            repeats=args.repeats,
        )
        print_reasoning_report(reasoning_results)
        metrics = calculate_reasoning_metrics(reasoning_results)
        if metrics.accepted_unsupported_citation_count or metrics.retained_row_count:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
