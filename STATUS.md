# ResolveAI — Current Status

## Current phase

Phase 4 — User Interface is complete.

Phase 5 — Observability is complete.

Phase 5.1 manual tracing is complete.

Phase 5.2 retrieval trace decomposition is complete.

Phase 6 — Productionization is the current phase.

Phase 6.1 — Docker is complete.

Phase 6.2 — CI is next and has not started.

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

## Phase 5 — Observability

Phase 5 grew from observed visibility gaps rather than an upfront technology
stack or fixed span design:

```text
multi-step investigation
→ insufficient request/result visibility
→ manual OpenTelemetry tracing
→ retrieval observed as dominant fake-path latency
→ retrieval span found too coarse
→ embedding/database decomposition
→ bottleneck localized
```

### Phase 5.1 — Manual investigation tracing

The first observability milestone answers one concrete operational question:

> When an investigation is slow or fails, was the time or failure in semantic
> retrieval, hypothesis generation, or citation verification?

ResolveAI now creates one opt-in OpenTelemetry trace around the existing
synchronous domain workflow:

```text
investigation
├── retrieve_runbooks
├── generate_hypothesis
└── verify_citations       # diagnosed path only
```

`RESOLVEAI_TRACE_CONSOLE=1` configures a batched console exporter with
`service.name = resolveai`. Without that flag, no SDK provider or exporter is
configured and ordinary execution remains quiet. Instrumentation uses explicit
application spans; no automatic FastAPI, psycopg, or model instrumentation was
added.

The trace semantics preserve the application semantics:

- diagnosed and inconclusive results are successful executions with an unset
  OpenTelemetry status and an explicit domain outcome attribute;
- `InsufficientEvidenceError` is handled inside the reasoning span and does not
  become an error;
- retrieval, reasoning, and citation exceptions escape normally and mark the
  active operation and root investigation spans as errors;
- attributes contain identifiers, categorical values, and counts rather than
  incident descriptions, Evidence content, runbook content, prompts, vectors,
  database URLs, or secrets.

### First local trace measurements

The manual smoke test used the deterministic fake with the existing local
PostgreSQL corpus. These are observations from two individual local requests,
not benchmarks or performance guarantees:

| Incident and outcome | investigation | retrieve_runbooks | generate_hypothesis | verify_citations |
|---|---:|---:|---:|---:|
| `INC-001` diagnosed | 244.789 ms | 244.482 ms | 0.040 ms | 0.008 ms |
| `INC-003` inconclusive | 19.245 ms | 19.092 ms | 0.024 ms | not executed |

The fake-reasoner measurements describe only local deterministic Python rules;
they do not represent GPT-5.6 Luna or provider latency. A separate safe smoke
test pointed retrieval at a closed local PostgreSQL port. The request returned
HTTP 500, and both `retrieve_runbooks` and `investigation` were exported with
`ERROR` status without modifying the real database.

These measurements established that semantic retrieval dominated the
deterministic-fake path and varied substantially between the two requests. The
original span could not reveal whether embedding or PostgreSQL work caused that
variation. That specific limitation justified Phase 5.2.

Phase 5.1 exit status: complete.

### Phase 5.2 — Retrieval trace decomposition

Phase 5.1 showed that `retrieve_runbooks` dominated the deterministic-fake API
path but combined query embedding with PostgreSQL/pgvector search. Phase 5.2
adds only the two child spans needed to distinguish those operations:

```text
retrieve_runbooks
├── generate_query_embedding
└── query_runbooks
```

`generate_query_embedding` covers the existing FastEmbed query operation and
records the fixed model and returned vector dimensions. `query_runbooks` covers
PostgreSQL connection, pgvector SQL execution, row fetching, and
`RetrievedRunbook` validation. Retrieval exceptions continue to propagate and
mark the active child, `retrieve_runbooks`, and `investigation` as errors.

Five sequential `INC-001` investigations were measured in one local FastAPI
process with console tracing enabled and the deterministic fake reasoner:

| Run | investigation | retrieve_runbooks | generate_query_embedding | query_runbooks | generate_hypothesis | verify_citations |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 170.652 ms | 170.444 ms | 152.787 ms | 17.367 ms | 0.038 ms | 0.006 ms |
| 2 | 21.411 ms | 21.230 ms | 7.569 ms | 13.384 ms | 0.031 ms | 0.005 ms |
| 3 | 15.692 ms | 15.532 ms | 4.557 ms | 10.698 ms | 0.025 ms | 0.005 ms |
| 4 | 18.710 ms | 18.540 ms | 4.390 ms | 13.879 ms | 0.028 ms | 0.005 ms |
| 5 | 22.636 ms | 22.465 ms | 4.381 ms | 17.808 ms | 0.025 ms | 0.004 ms |

The first request spent 152.787 ms inside query embedding. Subsequent same-process
calls spent approximately 4–8 ms. The observed pattern is consistent with
one-time or warm-up work in the embedding path, but these spans do not establish
whether model loading, caching, initialization, or another mechanism caused it.

After the first request, PostgreSQL/pgvector work measured approximately 10–18
ms and accounted for most semantic-retrieval time. PostgreSQL/pgvector is the
largest measured component of warm semantic retrieval, but the observed
duration is not itself evidence of a performance problem. No optimization is
justified by these measurements.

On this deterministic-fake path, `generate_hypothesis` measured approximately
0.025–0.038 ms and `verify_citations` measured approximately 0.004–0.006 ms.
Neither contributes materially to observed latency. Citation verification
remains a useful failure boundary rather than a performance boundary. Fake
reasoner latency is not representative of GPT-5.6 Luna or remote-provider
latency, and no live model call was needed to close Phase 5.

### Outcome and failure semantics

The focused in-memory trace test and local smoke tests verified:

```text
diagnosed
→ successful trace
```

```text
inconclusive
→ successful trace
→ reasoning outcome = inconclusive
→ no citation span
```

```text
retrieval/database failure
→ query_runbooks ERROR
→ retrieve_runbooks ERROR
→ investigation ERROR
→ original exception propagates
```

The genuine failure path was exercised safely by pointing one local process at a
closed PostgreSQL port. It returned HTTP 500 and exported the expected error
spans without modifying the real database.

### Why instrumentation stops here

The final trace hierarchy is:

```text
investigation
├── retrieve_runbooks
│   ├── generate_query_embedding
│   └── query_runbooks
├── generate_hypothesis
└── verify_citations       # diagnosed path only
```

The measurements do not justify splitting embedding into initialization versus
inference or splitting database work into connection acquisition, SQL execution,
fetching, and validation. The current spans answer the demonstrated operational
question without obscuring the domain workflow.

> Span granularity should increase only when an existing span becomes too coarse
> to answer a demonstrated operational question.

Phase 5.2 answered the current retrieval question.

### Deliberately postponed observability options

Prometheus and OpenTelemetry metrics remain intentionally deferred. Aggregate
questions such as investigation throughput, latency distribution,
diagnosed/inconclusive rate, retrieval failure rate, and reasoner failure rate
could become useful in a continuously running system. ResolveAI currently has no
sustained workload, SLO, or recurring monitoring requirement that would make
retaining those time series useful.

Grafana remains deferred because there is no retained metrics backend, retained
trace backend, or operational dashboard question requiring repeated
visualization. Console tracing sufficiently answers the current
single-investigation debugging question. There is no mandatory OpenTelemetry →
Prometheus → Grafana sequence.

Automatic FastAPI, psycopg, OpenAI/OpenRouter, and frontend instrumentation also
remain deferred, as do OTLP export and a Collector. Manual domain spans keep the
meaningful investigation workflow visible and already answer the current
question.

Known visibility limitations are:

- no HTTP parent span;
- 404 and pre-investigation failures may occur outside the domain trace;
- no real-provider timing has been measured;
- console traces are not retained;
- no cross-process trace propagation exists.

These are known limitations, not automatic implementation tasks. The existing
`generate_hypothesis` span is positioned to measure provider latency if a future
runtime requirement uses a real reasoner.

### Phase 5 conclusion

Phase 5 demonstrated that observability is valuable because it changed what is
known about the running application:

```text
observability
→ exposed where latency actually occurred
→ justified one finer measurement
→ showed first-call embedding behavior
→ showed warm PostgreSQL retrieval latency
→ prevented unsupported optimization work
```

No dependency, exporter, metrics system, retained telemetry backend, or runtime
optimization was added for Phase 5.2.

The completed architectural progression was:

```text
operational question
→ smallest useful signal
→ measurement
→ observed limitation
→ one justified refinement
→ question answered
→ stop
```

Phase 5.1 exit status: complete.
Phase 5.2 exit status: complete.
Phase 5 exit status: complete.

## Phase 6.1 — Docker

Phase 6.1 was implemented in two slices. The first packaged FastAPI beside the
existing PostgreSQL service while Next.js remained on the host. The second
packaged the production Next.js application and completed this topology:

```text
Compose
├── database   PostgreSQL + pgvector
├── api        FastAPI
└── web        Next.js production server
```

The root `Dockerfile` is a readable single-stage Python 3.13 image. It installs
the repository's locked non-development dependencies with uv, copies the
`resolve_ai` package, exposes container port 8000, and starts
`resolve_ai.api:app` with Uvicorn bound to `0.0.0.0:8000`. `.dockerignore` keeps
the local virtual environment, `.env`, caches, and generated frontend files out
of the build context.

The `api` Compose service publishes container port 8000 on host port 8000 and
receives this local Compose connection string:

```text
postgresql://resolveai:resolveai@database:5432/resolveai
```

`database` is the PostgreSQL service's DNS name on the Compose network. The
existing database image, initialization bind mount, named data volume, and host
port remain unchanged. pgvector remains an extension in that PostgreSQL service,
not a separate service.

No database readiness mechanism was added. FastAPI startup imports the
application without connecting to PostgreSQL; the database URL is read and the
connection is opened only when an investigation executes retrieval. Compose
startup ordering is therefore sufficient for this local slice.

The frontend `web/Dockerfile` is a separate single-stage Node 24 image. It uses
the pnpm 11.21.0 version pinned by the project, installs the frozen lockfile,
builds the existing Next.js application, exposes port 3000, and runs the
production `next start` script. Its build context is `web/`, so
`web/.dockerignore` independently excludes host dependencies, build output,
local environment files, and TypeScript build state.

The current rewrite configuration reads `RESOLVEAI_API_URL` while
`next.config.ts` runs. `next build` resolves that value and writes
`http://api:8000/:path*` into the production routes manifest. The web service
therefore receives `http://api:8000` at build time, and Compose also supplies the
same value at startup for consistent config evaluation. Requests use the built
rewrite; changing only the startup environment does not dynamically replace it.

Neither Next.js startup nor FastAPI startup requires its downstream service to
be ready. The Compose dependency chain expresses understandable startup order
without health checks, wait scripts, or custom entrypoints.

The final containerized smoke test confirmed all three services remained
running, the production page loaded through host port 3000, and frontend GET and
POST `/api` requests reached FastAPI from the web container's Compose-network IP.
`INC-001` produced the expected connection-pool diagnosis with three retrieved
runbooks. FastAPI connected through `database:5432`; pgvector remained installed,
all nine runbooks remained present, and zero embeddings were missing. The test
used the deterministic fake and made no model API call. No stored embeddings
were regenerated or overwritten.

Deliberately postponed:

- production deployment configuration;
- multi-stage builds, image hardening, and image-size optimization;
- retained FastEmbed model caching across API-container replacement;
- a reverse proxy in front of the two application services;
- automatic embedding-population or database-wait services;
- CI, image publishing, AWS, and Terraform.

Phase 6.1 API-container slice status: complete.
Phase 6.1 frontend-container slice status: complete.
Phase 6.1 exit status: complete.

## Verification status

- 60 deterministic tests pass without a model API call.
- 2 PostgreSQL integration tests are deliberately skipped in the ordinary run
  because one resets all stored embeddings to exercise population behavior.
- Live PostgreSQL contains all nine runbooks with no missing embeddings.
- Ruff lint and formatting checks pass.
- The uv dependency lock and Git diff validation pass.
- Frontend TypeScript validation, ESLint, and the Next.js production build pass.
- The three-service Compose smoke test passed for the production frontend,
  same-origin API rewrite, deterministic investigation, and database retrieval.

## Next phase

Phase 6.2 — CI is next, but no CI implementation has begun.
