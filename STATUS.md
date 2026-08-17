# ResolveAI — Current Status

## Current phase

Phase 4 — User Interface is complete.

Phase 5 — Observability is complete.

Phase 5.1 manual tracing is complete.

Phase 5.2 retrieval trace decomposition is complete.

Phase 6 — Productionization is complete.

Phase 6.1 — Docker is complete.

Phase 6.2 — CI is complete.

Phase 6.3 — Public Portfolio Deployment is complete.

Phase 6.3.1 — Northflank Sandbox confirmation is complete.

Phase 6.3.2 — Private PostgreSQL + pgvector initialization is complete.

Phase 6.3.3 — Private FastAPI deployment and resource-fit verification is
complete.

Phase 6.3.4 — Public Next.js deployment and browser-level reviewer-flow
verification are complete.

Phase 7.1 — Versioned runtime incident input is complete, deployed to Northflank,
and browser-smoke verified.

Phase 7.2 — Controlled real-model runtime reasoning is implemented and verified
locally. Its Northflank secret configuration, deployment, and live-provider smoke
test remain pending.

The post-deployment product robustness review is complete. Runtime input and
controlled live reasoning are implemented; later knowledge ingestion,
persistence, accounts, and Phase 8 work have not started.

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
- image publishing, AWS, and Terraform.

Phase 6.1 API-container slice status: complete.
Phase 6.1 frontend-container slice status: complete.
Phase 6.1 exit status: complete.

## Phase 6.2 — CI

The first CI workflow is implemented in `.github/workflows/ci.yml`. Every push
and pull request starts two independent Ubuntu jobs that can run in parallel:

```text
GitHub Actions
├── backend
│   ├── Python 3.13 and uv 0.11.6
│   ├── uv lock validation
│   ├── Ruff lint and format checks
│   └── deterministic pytest suite
└── frontend
    ├── Node 24 and pnpm 11.21.0
    ├── frozen dependency installation
    ├── TypeScript and ESLint checks
    └── Next.js production build
```

The jobs do not depend on each other. The backend job starts no PostgreSQL
service and supplies no database or model credentials; its two PostgreSQL
integration tests remain deliberately skipped. The frontend build does not
start or contact FastAPI.

Validation happened in two distinct stages:

```text
local verification
→ workflow implementation validated against existing commands

GitHub-hosted verification
→ backend job green
→ frontend job green
```

Local verification showed that ResolveAI worked in the developer environment.
The successful GitHub-hosted run, externally verified after the workflow was
pushed, showed that its declared setup and commands also work on clean external
runners rather than depending on developer-machine state.

> ResolveAI now automatically verifies its backend and frontend verification
> contracts on GitHub-hosted runners for pushes and pull requests.

The first slice deliberately omits PostgreSQL integration tests because they are
not part of the deterministic default suite and one resets stored embeddings.
Model evaluations remain measurements rather than deterministic CI regressions.
Docker image verification has not been shown to be necessary for every change.
Caching and version matrices have no measured need, while publishing and cloud
deployment belong to the next productionization phase.

Phase 6.2 exit status: complete.

## Phase 6.3 — Public portfolio deployment

The immediate deployment direction changed from AWS ECS/Fargate and Terraform
to Northflank Sandbox. ResolveAI is a hobby and portfolio project whose current
goal is a public demonstration at zero ongoing hosting cost. The Docker and CI
work remains valid: Docker proves reproducible packaging, GitHub Actions verifies
the application, and Northflank supplies the smallest managed public runtime.

The target topology is:

```text
browser
   ↓ public HTTPS
Northflank web :3000                         deployed and browser verified
   ↓ server-side /api rewrite, private HTTP
Northflank api :8000                         deployed
   ↓ private PostgreSQL connection
Northflank PostgreSQL + pgvector             ready
```

### Phase 6.3.1 — Sandbox confirmation

The free Sandbox allowance was confirmed to fit one project containing two
services and one PostgreSQL addon. The project deliberately uses the included
resource sizes and does not add paid capacity, uptime workarounds, or unrelated
services.

Phase 6.3.1 exit status: complete.

### Phase 6.3.2 — Database initialization

A private Northflank PostgreSQL addon now contains the ResolveAI database. The
existing `database/init.sql` enabled pgvector, created the schema and indexes,
and inserted or updated the frozen nine-runbook corpus. The existing explicit
FastEmbed population command generated the stored 384-dimensional embeddings;
all nine runbooks have an embedding.

Provisioning the addon and initializing ResolveAI were kept separate. Database
initialization was a deliberate one-time operation, not an API startup side
effect or an always-running service. It made no OpenAI or OpenRouter request.
The standard application connection is used at runtime, while the administrator
connection is reserved for setup and maintenance.

Phase 6.3.2 exit status: complete.

### Phase 6.3.3 — Private FastAPI and resource fit

The `api` combined service builds the existing repository-root `Dockerfile` and
runs the existing Uvicorn command on `0.0.0.0:8000`. The port is configured as a
private Northflank HTTP port. The PostgreSQL addon's standard `POSTGRES_URI` is
linked through a runtime secret group under the alias `DATABASE_URL`; no database
credential or model-provider credential is committed.

Runtime verification showed:

- the container saw `DATABASE_URL` without exposing its value;
- a direct database check returned nine runbooks and nine embeddings;
- `GET /incidents` returned HTTP 200;
- cold and warm `INC-001` investigations returned HTTP 200;
- the deterministic fake completed without an external model call;
- semantic retrieval returned three runbooks;
- repeated warm requests remained stable without an OOM or container restart.

The free API service has a 512 MiB memory limit. Observed memory was:

```text
pre-model API footprint  approximately 110 MiB
cold FastEmbed peak      approximately 440 MiB  (86%)
warm retained footprint  approximately 320 MiB  (63%)
```

The cold peak leaves limited margin, but the model remains cached and normal
warm investigations stay within an acceptable range. This is sufficient for the
intended low-concurrency portfolio demonstration. Simultaneous cold
initialization is outside the Sandbox workload contract and remains a documented
capacity limitation rather than a reason to add paid infrastructure now.

Phase 6.3.3 exit status: complete.

### Phase 6.3.4 — Public Next.js and end-to-end verification

The existing production Next.js container is deployed at:

```text
https://p01--web--2g46kqjy6mpk.code.run/
```

The service exposes public HTTPS on port 3000 and was built with
`RESOLVEAI_API_URL=http://api:8000`, preserving the intended same-origin browser
path through the private FastAPI service.

An independent direct HTTPS smoke test from the development environment passed:

- `GET /` returned HTTP 200 with valid TLS and the Next.js application;
- `GET /api/incidents` returned HTTP 200 with `INC-001` through `INC-003`;
- `POST /api/incidents/INC-001/investigate` returned HTTP 200 with the expected
  connection-pool diagnosis, verified supporting Evidence, and three retrieved
  runbooks;
- `POST /api/incidents/INC-003/investigate` returned HTTP 200 with the expected
  successful `inconclusive` outcome and no invented diagnosis;
- a repeated warm `INC-001` investigation returned HTTP 200;
- every tested request remained on the public Next.js origin under `/api`; no
  client request was redirected to the private API hostname.

The reviewer-facing browser check ran in headless Chromium from the cached
Docker `mcp/playwright` image against the public HTTPS deployment:

```text
open public HTTPS URL                                 passed
render INC-001, INC-002, and INC-003                  passed
run INC-001 and render diagnosed presentation         passed
distinguish 3 collected / 2 supporting Evidence items passed
render 3 RetrievedRunbooks in a separate section      passed
run INC-003 and render successful inconclusive state  passed
keep GET/POST browser requests on same-origin /api     passed
avoid failed requests, page errors, and layout overflow passed
```

The three observed browser API responses were HTTP 200 for `GET /api/incidents`,
`POST /api/incidents/INC-001/investigate`, and
`POST /api/incidents/INC-003/investigate`. Supporting Evidence used a distinct
green accent, role label, border, and background; uncited collected context used
neutral styling; retrieved guidance remained in its own labelled section. The
captured diagnosed and inconclusive pages showed no material rendering issue at
a 1440 by 900 viewport and no horizontal overflow.

Chromium reported one 404 for the optional `/favicon.ico`. It did not affect an
application asset, API request, interaction, or rendered result and is therefore
recorded as non-material. There were no failed requests, uncaught page errors,
or other console errors.

Phase 6.3.4 exit status: complete.
Phase 6.3 exit status: complete.
Phase 6 exit status: complete.

As recorded at Phase 6 close, Phase 7.1 was not started inside that deployment
verification slice.

## Phase 7.1 — Versioned runtime incident input

Phase 7.1 introduces a separate bounded public transport contract without
changing the frozen `IncidentContext` fixture representation. A version-1
`RuntimeIncidentBundle` contains one incident and between one and fifty
normalized Evidence items. Validation rejects unknown fields and schema
versions, ambiguous timestamps, duplicate Evidence IDs, invalid identifier
shapes, oversized text/detail collections, and unsupported field values.

Both input worlds now adapt into one shared domain boundary:

```text
prepared fixture
→ inspect logs and deployments
→ Incident + Evidence[]
                         ↘
                           investigate_evidence()
                         ↗
runtime JSON bundle
→ validate and adapt
→ Incident + Evidence[]
```

`POST /runtime/investigate` processes the bundle synchronously and transiently.
It does not insert incidents or Evidence into PostgreSQL, mutate fixture data,
change benchmark inputs, create accounts, retain investigation history, accept
file uploads, or introduce CRUD/repository infrastructure. Retrieval continues
to use the frozen nine-runbook corpus.

The Next.js application now exposes two clearly labelled tabs: Guided demo and
Runtime JSON. The runtime path supplies an editable novel example, discloses the
deterministic reasoner and non-retention policy, renders the existing diagnosed
or inconclusive result components, and distinguishes malformed JSON from
server-side validation feedback.

Local browser verification through the `docker_insta_ai` Playwright MCP passed:

```text
prepared INC-001 diagnosis                              passed
novel USER-INC-901 diagnosis                            passed
3 collected / 2 cited runtime Evidence items            passed
3 retrieved runbooks kept separate                      passed
client-side malformed JSON feedback                     passed
server-side schema validation feedback                  passed
same-origin /api prepared and runtime requests          passed
390px viewport without horizontal overflow              passed
```

The successful runtime request cited only caller-supplied Evidence IDs and
returned the expected connection-pool diagnosis. A separate deterministic API
test proves that novel evidence outside the fake patterns returns a successful
inconclusive result. The guided fixture list remains exactly `INC-001` through
`INC-003` after runtime requests.

The rebuilt local Compose stack passed both reviewer paths. The successful flow
had no page errors or failed application requests; `/favicon.ico` retains the
previously documented non-material 404. The deliberate invalid-bundle browser
exercise produced its expected HTTP 422 and readable validation message.

Phase 7.1 answers its learning question:

> A previously unseen, versioned incident bundle can pass through ResolveAI's
> existing investigation workflow without becoming a fixture or persisted row.

This proved generalized input, not generalized reasoning. At Phase 7.1 close the
deterministic fake still recognized only two patterns and the runtime output
taxonomy remained benchmark-shaped. Phase 7.2 owns that model/runtime pressure.

The pushed Phase 7.1 build passed GitHub Actions and deployed through Northflank.
Public browser smoke verification repeated the guided diagnosed and inconclusive
flows, the runtime diagnosed and inconclusive flows, input-validation feedback,
same-origin API routing, and a 390px layout check. No material regression was
found; the optional favicon 404 remains the only non-material asset error.

Phase 7.1 exit status: complete and publicly verified.

## Phase 7.2 — Controlled real-model runtime reasoning

Phase 7.2 keeps the prepared guided demo on `evidence-only-fake-v1` and routes
only `POST /runtime/investigate` through one explicit server-side provider. The
`RESOLVEAI_RUNTIME_PROVIDER` environment value selects `openrouter` or `openai`;
there is no browser provider dropdown, user-supplied key, automatic routing,
cross-provider retry, or deterministic fallback. The intended production value
is `openrouter` with a capped `OPENROUTER_API_KEY`.

Both providers use the Responses API and GPT-5.6 Luna through the existing
OpenAI-compatible adapter. Requests use structured output, `medium` reasoning,
a 4,000-token output ceiling, a 30-second client timeout, zero SDK retries, and
one process-local concurrent live request. Stable public failures distinguish a
busy reasoner (429), invalid model output or citations (502), unavailable or
misconfigured inference (503), and provider timeout (504). Provider details and
credentials never appear in error responses, and failures never invoke the fake.

Runtime decisions now accept a bounded lowercase snake-case label instead of
the evaluator's six-value `RootCauseLabel`. The frozen benchmark retains that
enum and explicitly projects application output back into it for scoring, so an
outside-taxonomy runtime cause is an ordinary benchmark mismatch rather than a
schema failure. Every investigation response also includes safe `provider` and
`model` metadata.

`GET /runtime/reasoner` exposes only that safe metadata. The Runtime JSON UI
shows the active provider/model, explains that input reaches an external
provider and is not persisted by ResolveAI, warns against submitting secrets,
and keeps the guided path visually and behaviorally deterministic.

The deterministic suite makes no provider call. An opt-in spend-bearing runtime
evaluation covers lock contention, a provider outage, an outside-taxonomy DNS
failure, and insufficient evidence for three repetitions by default:

```bash
RESOLVEAI_RUNTIME_PROVIDER=openrouter \
OPENROUTER_API_KEY=... \
uv run python -m evals.evaluate_runtime_reasoning \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai \
  --repeats 3
```

Local implementation verification passes. Deployment remains deliberately
pending until a capped OpenRouter key and `RESOLVEAI_RUNTIME_PROVIDER=openrouter`
are configured on the private API service.

## Product robustness design decision

At Phase 6 close, repository inspection confirmed that ResolveAI demonstrated a
strong synthetic investigation and evaluation architecture, not yet a general
incident product:

- the public API lists only `INC-001` through `INC-003` from Python fixtures;
- users could select a fixture but could not provide a novel incident or Evidence;
- the nine runbooks and their embeddings are the only application knowledge
  persisted in PostgreSQL;
- the default fake reasoner handles two explicit evidence patterns;
- real OpenAI and OpenRouter reasoners are evaluator/manual-path capabilities,
  not the public runtime default;
- investigation results and provenance are transient;
- citation verification proves that cited Evidence IDs were collected, not that
  a citation semantically entails the diagnosis.

That limitation is acceptable for Phase 6.3, whose question is public
accessibility. It would be a material limitation if treated as the project's final
portfolio state.

The approved next-stage direction is an explicit two-world architecture:

```text
ResolveAI
├── evaluation world
│   ├── frozen synthetic incidents and expected outcomes
│   ├── frozen retrieval cases and benchmark corpus
│   └── reproducible model/retrieval measurements
└── runtime world
    ├── user-supplied Incident and normalized Evidence
    ├── scoped KnowledgeDocument data and embeddings
    ├── controlled real-model investigations
    └── later: immutable InvestigationRun provenance
```

Evaluation fixtures, hashes, labels, and benchmark retrieval inputs remain
immutable. Mutable runtime rows must not affect benchmark retrieval or expected
results. The worlds should share the ordinary Python investigation workflow,
retrieval implementation, structured-output validation, and citation verification
through explicit adapters. Benchmark-specific closed taxonomies, including the
current root-cause labels, must not constrain arbitrary runtime diagnoses.

The highest-value first proof was a transient, versioned JSON incident bundle.
Phase 7.1 supplied it without building CRUD, accounts, or a generic persistence
layer. Phase 7.2 now supplies controlled real-model runtime reasoning. Runtime
`KnowledgeDocument` ingestion remains the next separate measured slice. Only
after those paths prove useful should incidents, Evidence, and immutable
investigation snapshots become persisted product entities.

The public demo should eventually expose two honest paths:

- a prepared, deterministic guided demo for a fast and repeatable review;
- an own-data path using one fixed server-side real model with disclosed model
  metadata, strict input/request/cost limits, and no silent fake fallback.

The design review itself made no application, database, or deployment changes;
the Phase 7.1 and local Phase 7.2 implementations followed as separate slices.

## Verification status

- 80 deterministic tests pass without a model API call.
- 2 PostgreSQL integration tests are deliberately skipped in the ordinary run
  because one resets all stored embeddings to exercise population behavior.
- Local and Northflank PostgreSQL contain all nine runbooks with no missing
  embeddings.
- Ruff lint and formatting checks pass.
- The uv dependency lock and Git diff validation pass.
- Frontend TypeScript validation, ESLint, and the Next.js production build pass.
- The GitHub-hosted `backend` and `frontend` CI jobs both pass.
- The three-service Compose smoke test passed for the production frontend,
  same-origin API rewrite, prepared and runtime deterministic investigations,
  validation feedback, and database retrieval.
- The private Northflank FastAPI service passed database, cold-investigation,
  warm-investigation, retrieval, stability, and memory-fit checks.
- The public Northflank Next.js origin passed direct TLS, page, same-origin API,
  diagnosed, inconclusive, and repeated warm-request smoke checks.
- The public reviewer flow passed browser-level Chromium verification for all
  incident choices, the `INC-001` diagnosis, the `INC-003` inconclusive result,
  semantic section separation, and same-origin `/api` traffic.
- Browser verification found no failed requests, page errors, material console
  errors, rendering overlap, or horizontal overflow. The optional
  `/favicon.ico` returns a non-material 404.
- The public Phase 7.1 runtime path passed browser verification at desktop and
  390px widths with same-origin API traffic and clear invalid-input feedback.
- The local Phase 7.2 Python suite, frontend type/lint checks, and production
  frontend build pass without a live provider call.
- Rebuilt Phase 7.2 Compose images passed same-origin metadata and guided API
  checks plus browser verification of provider/privacy copy and 390px overflow.

## Next phase

Deploy and smoke-test Phase 7.2 after configuring the capped OpenRouter secret.
Its learning question remains:

> Can the runtime reason beyond the fake's two programmed evidence patterns?

Once live evaluation answers that question, plan Phase 7.3 runtime knowledge
ingestion. Persistence, accounts, and optional infrastructure remain out of
scope until those smaller runtime proofs justify them.
