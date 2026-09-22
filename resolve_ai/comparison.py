"""Prepare one immutable context, execute two branches, and own scoped cleanup."""

import hashlib
import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

from openai import APIError, APIResponseValidationError, APITimeoutError
from opentelemetry import trace
from pydantic import ValidationError
from typesafe_sdk import (
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeError,
)

from resolve_ai.comparison_models import (
    ComparisonBranch,
    ComparisonEvent,
    ComparisonFinished,
    ComparisonInput,
    PreparedComparison,
    Provider,
)
from resolve_ai.comparison_reasoner import (
    MODELS,
    ask,
    cause_questions,
    evidence_questions,
)
from resolve_ai.investigation import retrieve_investigation_references
from resolve_ai.retrieval import (
    RuntimeKnowledgeError,
    delete_runtime_knowledge_scope,
    store_runtime_knowledge_documents,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def execute_branch(
    provider: Provider, state: dict, candidates: list[str], origin: float, caller=ask
) -> ComparisonBranch:
    started_at = datetime.now(UTC)
    start = perf_counter()
    fields = {
        "provider": provider,
        "model": MODELS[provider],
        "started_at": started_at,
        "start_offset_ms": (start - origin) * 1000,
    }
    calls = []
    attempted_calls = 0
    with tracer.start_as_current_span(
        "compare_reasoner", attributes={"resolveai.reasoner.provider": provider}
    ):
        try:
            attempted_calls += 1
            cause_call = caller(
                provider, deepcopy(state), cause_questions(candidates), "cause"
            )
            calls.append(cause_call)
            choice = cause_call.answers["cause"]
            if choice == "none":
                return ComparisonBranch(
                    **fields,
                    outcome="inconclusive",
                    calls=calls,
                    attempted_calls=attempted_calls,
                    duration_ms=(perf_counter() - start) * 1000,
                )
            if choice not in {f"c{i}" for i in range(len(candidates))}:
                raise ValueError("Unknown candidate")
            index = int(choice[1:])
            questions = evidence_questions(state, candidates[index])
            attempted_calls += 1
            evidence_call = caller(provider, deepcopy(state), questions, "evidence")
            calls.append(evidence_call)
            if set(evidence_call.answers) != set(questions) or any(
                v not in ("supports", "contradicts", "unrelated")
                for v in evidence_call.answers.values()
            ):
                raise ValueError("Invalid evidence decision")
            relations = {
                item["id"]: evidence_call.answers[f"e{i}"]
                for i, item in enumerate(state["evidence"])
            }
            support = [key for key, value in relations.items() if value == "supports"]
            established = bool(support) and "contradicts" not in relations.values()
            return ComparisonBranch(
                **fields,
                outcome="supported" if established else "inconclusive",
                candidate_index=index if established else None,
                supporting_evidence_ids=support if established else [],
                evidence_relations=relations,
                calls=calls,
                attempted_calls=attempted_calls,
                duration_ms=(perf_counter() - start) * 1000,
            )
        except (APITimeoutError, TypeSafeAPITimeoutError):
            code = "timeout"
        except (
            ValueError,
            ValidationError,
            KeyError,
            APIResponseValidationError,
            TypeSafeAPIResponseValidationError,
        ):
            code = "invalid_output"
        except (APIError, TypeSafeError):
            code = "unavailable"
        except Exception:  # noqa: BLE001 - isolate the other provider; never emit exception bodies
            logger.error("Unexpected comparison branch failure for %s", provider)
            code = "internal_error"
    return ComparisonBranch(
        **fields,
        outcome="failed",
        error_code=code,
        calls=calls,
        attempted_calls=attempted_calls,
        duration_ms=(perf_counter() - start) * 1000,
    )


def run_comparison(
    request: ComparisonInput,
    database_url: str,
    emit: Callable[[ComparisonEvent], None],
    caller=ask,
) -> None:
    origin = perf_counter()
    started_at = datetime.now(UTC)
    scope = None
    cleanup = "not_needed"
    with tracer.start_as_current_span("comparison"):
        try:
            incident, evidence, documents = request.bundle.to_domain()
            if documents:
                scope = uuid4()
                store_runtime_knowledge_documents(
                    database_url=database_url,
                    scope_id=scope,
                    documents=documents,
                    expires_at=started_at + timedelta(minutes=15),
                )
            runbooks, references = retrieve_investigation_references(
                incident, evidence, database_url, scope
            )
            state = {
                "incident": incident.model_dump(mode="json"),
                "evidence": [e.model_dump(mode="json") for e in evidence],
                "references": [
                    r.model_dump(mode="json") for r in [*runbooks, *references]
                ],
            }
            # Reject oversized comparison contexts before either provider spends a call.
            for questions in [
                cause_questions(request.candidates),
                *[evidence_questions(state, c) for c in request.candidates],
            ]:
                if (
                    len(
                        json.dumps(
                            {"state": state, "questions": questions}, ensure_ascii=False
                        ).encode()
                    )
                    > 30_000
                ):
                    emit(ComparisonEvent(type="error", error="input_too_large"))
                    return
            fingerprint = hashlib.sha256(
                json.dumps(
                    {"state": state, "candidates": request.candidates}, sort_keys=True
                ).encode()
            ).hexdigest()
            emit(
                ComparisonEvent(
                    type="prepared",
                    prepared=PreparedComparison(
                        comparison_id=uuid4(),
                        input_sha256=fingerprint,
                        started_at=started_at,
                        preparation_ms=(perf_counter() - origin) * 1000,
                        candidates=request.candidates,
                        evidence=evidence,
                        runbooks=runbooks,
                        documents=references,
                    ),
                )
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        copy_context().run,
                        execute_branch,
                        p,
                        deepcopy(state),
                        list(request.candidates),
                        origin,
                        caller,
                    )
                    for p in ("openrouter", "jev")
                ]
                for future in as_completed(futures):
                    emit(ComparisonEvent(type="branch", branch=future.result()))
        except RuntimeKnowledgeError:
            emit(ComparisonEvent(type="error", error="preparation_unavailable"))
        except Exception:  # noqa: BLE001 - stream has started; retain a safe terminal failure
            logger.error("Unexpected comparison preparation failure")
            emit(ComparisonEvent(type="error", error="internal_error"))
        finally:
            if scope is not None:
                try:
                    delete_runtime_knowledge_scope(database_url, scope)
                    cleanup = "completed"
                except RuntimeKnowledgeError:
                    cleanup = "deferred"
                    logger.error("Comparison scope cleanup deferred to expiry purge")
            emit(
                ComparisonEvent(
                    type="finished",
                    finished=ComparisonFinished(
                        duration_ms=(perf_counter() - origin) * 1000, cleanup=cleanup
                    ),
                )
            )
