# ResolveAI — Current Status

## Current phase

Phase 4 — User Interface is complete.

Phase 5 — Observability is the current/next phase. Phase 5 has not started.

## Completed phases

### Phase 1 — Investigation Core

- FastAPI application with synthetic incidents, logs, and deployments
- deterministic evidence collection and citation verification
- evidence-only deterministic fake
- diagnosed and inconclusive structured results
- observed `Evidence` kept separate from supporting-evidence citations
- unit-tested plain-Python orchestration

Phase 1 exit status: complete.

### Phase 2 — Retrieval

- PostgreSQL weighted lexical retrieval
- FastEmbed with the fixed `BAAI/bge-small-en-v1.5` model
- persistent 384-dimensional document embeddings in pgvector
- explicit query embedding followed by parameterized vector SQL
- independent lexical and semantic evaluation
- semantic retrieval integrated into investigation as ordered `RetrievedRunbook[]`
- `RetrievedRunbook` kept separate from observed `Evidence`

The six-runbook Phase 2 benchmark measured:

```text
                         Direct    Paraphrased    Overall
Lexical                    5/6         0/6          5/12
Semantic                   6/6         5/6         11/12
```

Semantic retrieval had six unique wins and lexical retrieval had none. The
case-level criterion for hybrid retrieval was therefore not met.

Phase 2 exit status: complete.

### Phase 3 — Evaluation

Phase 3 added two frozen investigation slices:

- core benchmark: `INC-001` through `INC-007`;
- retrieval-dependent extension: `INC-008` through `INC-010`.

Together they provide ten complete synthetic `IncidentContext` cases with
model-independent normalized root causes, required and acceptable Evidence IDs,
relevant runbooks, remediation labels, and useful prohibited competitors.

The evaluator supports the deterministic fake, direct OpenAI, and OpenRouter
reasoners while preserving the same investigation workflow, Pydantic Structured
Outputs, prompt, evidence verification, and diagnosed/inconclusive result model.
The application itself still defaults to the deterministic fake.

## Evaluation semantics

The final evaluator taxonomy is:

- `correct_answer`: correct status and root cause with every required citation;
- `correct_with_extraneous_evidence`: correct diagnosis with real but
  non-supporting Evidence that reduces precision;
- `correct_inconclusive`: correct abstention on an inconclusive case;
- `incorrect_answer`: wrong status, wrong root cause, or missing required support;
- `unsupported_answer`: a correct root-cause conclusion that cites unavailable or
  unverifiable Evidence;
- `system_failure`: retrieval, API, schema, or other execution failure.

Unsupported citation IDs are also reported independently of the case outcome. A
wrong root cause remains `incorrect_answer` even when it also contains an unknown
citation.

Citation metrics apply only when the normalized diagnosed root cause is correct:

- recall uses `required_supporting_evidence_ids`;
- precision uses `acceptable_supporting_evidence_ids`;
- real Evidence outside the acceptable set reduces precision;
- unavailable Evidence is recorded as an unsupported citation;
- wrong diagnoses and correct inconclusive outcomes contribute to neither
  citation numerator nor denominator.

Root-cause accuracy excludes cases whose expected outcome is inconclusive.

## Deterministic fake baseline

The evidence-only fake remains deliberately narrow:

```text
Status accuracy:             3/7 (43%)
Root-cause accuracy:         2/6 (33%)
Evidence citation precision: 3/3 (100%)
Evidence citation recall:    3/3 (100%)
```

The citation recall denominator changed from the earlier `3/10` report because
the corrected metric now includes only correctly diagnosed root causes. The fake
quality result is an evaluation baseline, not a regression-test requirement.

## Retrieval quality at Phase 3 exit

The three organization-specific documents added for the retrieval-dependent
slice expanded the corpus to nine runbooks and the retrieval benchmark to
eighteen cases:

```text
                         Direct    Paraphrased    Overall
Lexical                    5/9         0/9          5/18
Semantic                   9/9         7/9          16/18
```

On the six new queries alone:

```text
Semantic Top-1:        5/6
Semantic Top-3:        6/6
```

The actual incident-derived query placed each required organization-specific
document first, while retaining confusable neighbors in the supplied Top-3.

## GPT-5.6 Luna measurements

The OpenRouter reasoner uses `openai/gpt-5.6-luna` through the Responses API with
Pydantic Structured Outputs and no explicit reasoning override.

### Frozen core benchmark

```text
Status accuracy:             7/7 (100%)
Root-cause accuracy:         6/6 (100%)
Evidence citation precision: 11/15 (73%)
Evidence citation recall:    10/10 (100%)
```

Removing retrieved runbooks produced identical case outputs and metrics. The
core cases therefore primarily measure reasoning over operational Evidence, not
knowledge augmentation.

### Retrieval-dependent benchmark

Three repetitions were run per condition, for nine case results per condition:

| Metric | With runbooks | Without runbooks |
|---|---:|---:|
| Status accuracy | 7/9 (78%) | 7/9 (78%) |
| Root-cause accuracy | 7/9 (78%) | 4/9 (44%) |
| Citation precision over correct diagnoses | 19/19 (100%) | 11/11 (100%) |
| Citation recall over correct diagnoses | 14/14 (100%) | 8/8 (100%) |
| Correct answers | 7/9 | 4/9 |
| Incorrect answers/outcomes | 2/9 | 5/9 |
| Unsupported citations | 0 | 0 |
| System failures | 0 | 0 |

The clearest effect was `INC-010`:

```text
with runbooks:    provider outage 2/3, inconclusive 1/3
without runbooks: worker backlog 3/3
```

The internal notification-lifecycle document removed the repeated competing
diagnosis. `INC-009` improved from 1/3 to 2/3 correct. `INC-008` remained 3/3
correct in both conditions and did not demonstrate retrieval value.

Phase 3 conclusion:

> Retrieved organization-specific knowledge demonstrated measurable
> investigation value for GPT-5.6 Luna on the frozen retrieval-dependent
> synthetic benchmark.

This is a benchmark-scoped finding, not a general claim about retrieval or RAG.

## Current application flow

```text
incident
→ collect operational Evidence
→ build deterministic retrieval query
→ semantic Top-3 retrieval
→ RetrievedRunbook[]
→ selected HypothesisGenerator
→ structured Hypothesis or inconclusive signal
→ citation verification
→ Diagnosis / inconclusive
→ InvestigationResult
```

Similarity remains retrieval relevance, not causal Evidence or diagnosis
confidence. Only observed Evidence IDs may become supporting citations.

## Known limitations

- The investigation benchmark contains only ten entirely synthetic cases.
- The retrieval-dependent extension contains only three cases.
- Real-model behavior is nondeterministic.
- `INC-009` and `INC-010` were not perfectly stable with retrieval.
- `INC-008` did not demonstrate retrieval value.
- Retrieval utility was measured only with GPT-5.6 Luna.
- No prompt optimization or model comparison was performed.
- No hybrid retrieval, reranking, or query-rewriting experiment was justified.

These are recorded limitations, not immediate implementation tasks.

## Architectural conclusions

- Semantic retrieval remains the selected investigation retrieval strategy.
- Hybrid retrieval is not justified by the current case-level evidence.
- Retrieved knowledge and observed Evidence must remain separate domain concepts.
- Citation verification remains deterministic application behavior.
- The fake remains useful as a deterministic test double, while Luna provides the
  measured reasoning baseline.
- No LangChain, LangGraph, provider registry, routing, or fallback layer is needed.

## Phase 4 — User Interface

Phase 4 added the smallest reviewer-facing interface needed to make the existing
application behavior understandable without requiring a reviewer to read raw
FastAPI JSON. The completed flow is:

```text
open ResolveAI
→ view synthetic incidents
→ select an incident
→ run investigation
→ understand diagnosed or inconclusive result
→ distinguish collected Evidence from supporting Evidence
→ inspect RetrievedRunbooks separately
```

The implementation under `web/` is a Next.js + TypeScript App Router
application with one responsive dashboard. One client-side workspace owns the
transient incident selection, request state, result, and error state using
ordinary React state. Native `fetch` calls same-origin `/api` paths, and a
configurable Next.js rewrite uses `RESOLVEAI_API_URL` to reach FastAPI without a
FastAPI CORS change.

The interface provides:

- incident selection and basic incident context;
- one synchronous investigation request;
- diagnosed and inconclusive result presentation;
- confidence, remediation, and informational human-approval policy when a
  diagnosis exists;
- every collected Evidence item in API order;
- visual highlighting of the subset cited by
  `Diagnosis.supporting_evidence_ids`;
- `RetrievedRunbook` values in a separate reference-knowledge section;
- incident-list, network, API, 404, and unexpected-response handling;
- responsive presentation with plain CSS.

No global frontend state, persistence, complex routing, component library, or
additional data-fetching framework was required for one page and one transient
investigation.

### Phase 4 architectural decisions

#### Synchronous UI before progress infrastructure

The backend returns only one final synchronous `InvestigationResult`. The UI
therefore exposes only truthful request-level states:

```text
Ready
Investigating
Complete
Failed
```

`inconclusive` is a successful completed investigation outcome, not a request or
system failure. No internal investigation timeline, percentage, or workflow
event was invented.

#### Evidence remains distinct from reference knowledge

The UI preserves the established domain distinction:

```text
collected Evidence
≠ supporting Evidence
≠ RetrievedRunbook
```

Supporting Evidence is the cited subset identified by
`Diagnosis.supporting_evidence_ids`. Runbooks remain separately labelled
reference knowledge, and their similarity represents retrieval relevance rather
than causal support or diagnosis confidence.

#### Human approval remains informational

`human_approval_required` is displayed as policy information together with an
explicit statement that no action was performed. There is no `Approve` control
because ResolveAI currently recommends remediation but exposes no mutating
remediation workflow.

#### No frontend architecture without a requirement

The implemented flow did not justify Redux, Zustand, TanStack Query, frontend
persistence, complex routing, a component library, or browser E2E
infrastructure. Ordinary local React state and native `fetch` keep the complete
data flow visible.

### Live local smoke test

The first UI slice was manually exercised with PostgreSQL, FastAPI, and Next.js
running together in a real local environment. This was a smoke test, not
automated browser coverage. It confirmed:

- `INC-001` rendered the diagnosed connection-pool exhaustion result, visibly
  distinguished cited Evidence from collected context, and displayed confidence,
  remediation, the approval notice, and RetrievedRunbooks in their separate
  section;
- `INC-002` rendered the expired-client-certificate diagnosis and its citation
  presentation correctly;
- `INC-003` completed successfully as inconclusive without an invented
  `Diagnosis`, while its collected Evidence and reference knowledge remained
  visible;
- the Next.js rewrite preserved and displayed the existing FastAPI 404 detail
  for an unknown incident.

### Why Phase 4 is complete

The long-term project description mentions possible progress timelines, tool
calls, intermediate hypotheses, and approval controls. These are not current UI
requirements because the backend exposes none of the corresponding workflows or
events. Adding backend infrastructure solely to reproduce an aspirational UI
diagram would violate the project's incremental architecture principle.

> UI capability should follow real application capability.

Progress visualization should be reconsidered only when the backend exposes
meaningful investigation events or investigation latency demonstrates a user
experience problem. Approval controls should be introduced only when an actual
mutating action exists.

Phase 4 exit status: complete.

## Verification status

- 59 deterministic tests pass without a model API call.
- 2 PostgreSQL integration tests are deliberately skipped in the ordinary run
  because one resets all stored embeddings to exercise population behavior.
- Live PostgreSQL contains all nine runbooks with no missing embeddings.
- Ruff lint and formatting checks pass.
- The uv dependency lock and Git diff validation pass.
- Frontend TypeScript validation, ESLint, and the Next.js production build pass.
- The local PostgreSQL + FastAPI + Next.js smoke test passed for `INC-001`,
  `INC-002`, `INC-003`, and the proxied FastAPI 404 response.

## Next phase

Phase 5 — Observability is next, but no Phase 5 implementation has begun.

Immediate starting question:

> A ResolveAI investigation now contains multiple meaningful internal operations,
> but operational visibility is still primarily at the request/result level.
> Determine what observability is now justified before introducing OpenTelemetry,
> Prometheus, or Grafana.

Phase 5 should continue the same process:

```text
identify operational question
→ choose smallest observable signal
→ measure limitation
→ add complexity only when justified
```
