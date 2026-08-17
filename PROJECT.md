# File Purpose
│  What are we building?
│  Why does it exist?
│  What architecture are we aiming toward?
│  What are the phases?
│  Why were technologies chosen?

# ResolveAI

## AI Incident Investigation Copilot

ResolveAI is a production-oriented AI engineering portfolio project built to
investigate software incidents by combining structured operational data,
retrieval, LLM reasoning, evaluation, observability, and public deployment. Its
current implementation and objective benchmark use deliberately synthetic data;
the next major capability will accept bounded user-supplied runtime data without
making the benchmark mutable.

The project has two equally important goals:

1. Build a credible end-to-end AI engineering project suitable for a professional portfolio.
2. Learn the software engineering and AI engineering concepts involved well enough to explain and defend the architecture during a technical interview.

The project should therefore favor **clarity, incremental complexity, measurable improvements, and explicit architectural reasoning** over unnecessary sophistication.

---

# 1. Project Goal

ResolveAI should answer questions such as:

> “The payments API started returning HTTP 500 errors after this morning's deployment. What is the likely cause?”

The system should investigate the incident using multiple sources of evidence rather than responding from a single prompt.

Possible evidence sources include:

- application logs;
- metrics;
- deployment history;
- Git commits;
- service documentation;
- runbooks;
- previous incidents;
- architecture documentation.

A final investigation should provide structured output such as:

- probable root cause;
- supporting evidence;
- confidence;
- source attribution;
- recommended remediation;
- whether human approval is required before taking action.

Example:

```text
Incident: INC-027

Probable root cause:
Database connection pool exhaustion.

Evidence:
- error rate increased at 10:37;
- deployment occurred at 10:31;
- database connection latency increased sharply;
- the latest configuration change reduced pool size from 20 to 5;
- a previous incident showed similar symptoms.

Recommended remediation:
Revert the connection-pool configuration.

Confidence:
0.87
```

The repository, tests, examples, and evaluation benchmark should use entirely
synthetic data. The future runtime may accept data deliberately supplied by a
user, but that data must remain outside version control and outside the frozen
benchmark. No real employer, banking, customer, secret, or confidential
production data should be included in the repository or documentation.

---

# 2. Main Engineering Principle

The system should begin simple and become more sophisticated only when a concrete requirement justifies the additional complexity.

The preferred progression is:

```text
simple implementation
        ↓
understand it
        ↓
test it
        ↓
measure its limitations
        ↓
introduce a justified improvement
```

Architecture should emerge from requirements.

The repository should not contain technologies, design patterns, or infrastructure merely because they are fashionable or common in enterprise systems.

A useful architectural question throughout the project is:

> What problem became difficult enough that this new technology is now justified?

---

# 3. Target Architecture

The long-term system may contain the following components:

```text
                        ┌─────────────────────┐
                        │   Next.js / React   │
                        │ Incident Dashboard  │
                        └──────────┬──────────┘
                                   │
                              REST / SSE
                                   │
                        ┌──────────▼──────────┐
                        │      FastAPI        │
                        │   Application API   │
                        └──────────┬──────────┘
                                   │
                     ┌─────────────▼─────────────┐
                     │ Investigation Workflow    │
                     │                           │
                     │ collect → retrieve        │
                     │    ↓         ↓            │
                     │ correlate → hypothesize   │
                     │    ↓                      │
                     │ verify → diagnose         │
                     └───┬────┬────┬────┬───────┘
                         │    │    │    │
             ┌───────────┘    │    │    └────────────┐
             ▼                ▼    ▼                 ▼
          Logs            Metrics  Deployments      Retrieval
                                                     │
                                      ┌──────────────▼─────────────┐
                                      │ PostgreSQL + pgvector      │
                                      │                            │
                                      │ runbooks                   │
                                      │ incidents                  │
                                      │ architecture docs          │
                                      │ service documentation      │
                                      └────────────────────────────┘
```

This is the long-term direction, not the starting implementation.

The next-stage architecture explicitly separates evaluation from runtime use:

```text
ResolveAI
│
├── Evaluation world
│   ├── frozen synthetic incidents and Evidence
│   ├── known ground truth and benchmark-only labels
│   ├── frozen retrieval cases and runbook corpus
│   └── repeatable retrieval/model evaluation
│
└── Runtime world
    ├── user-supplied Incident and Evidence
    ├── scoped KnowledgeDocument ingestion
    ├── controlled real-model reasoning
    └── later: immutable InvestigationRun history
```

These are not separate products. They should share the plain-Python
investigation workflow, retrieval operations, structured-output validation, and
citation verification. They must not share mutable data implicitly. Evaluation
fixtures, hashes, ground truth, and retrieval inputs remain immutable, while
runtime API models and storage may evolve without changing benchmark outcomes.

---

# 4. Development Phases

## PHASE 1 — INVESTIGATION CORE

Build the smallest useful vertical slice of ResolveAI.

### Goals

- Python application;
- FastAPI API;
- synthetic incident data;
- synthetic logs;
- synthetic deployment history;
- simple investigation workflow;
- structured Pydantic outputs;
- deterministic fake model where useful for testing;
- unit tests.

### Example flow

```text
incident
   ↓
load incident context
   ↓
inspect synthetic logs
   ↓
inspect deployment information
   ↓
generate hypothesis
   ↓
verify available evidence
   ↓
return diagnosis
```

Initially this workflow should preferably be implemented with ordinary Python functions.

LangGraph should only be introduced once branching, loops, retries, or persistent workflow state make plain Python orchestration noticeably awkward.

### Deliberately postponed

Do not introduce yet:

- cloud infrastructure;
- Terraform;
- Kubernetes;
- Prometheus;
- Grafana;
- a vector database;
- microservices;
- a message broker;
- complex frontend state management.

The Phase 1 objective is to prove that one incident can be investigated end-to-end.

---

# PHASE 2 — RETRIEVAL

Introduce a knowledge base containing synthetic:

- runbooks;
- previous incidents;
- service documentation;
- architecture documentation.

Use PostgreSQL as the primary database.

## 2.1 Lexical retrieval

Start with PostgreSQL full-text search.

Learn and expose the concepts involved:

- tokenization;
- lexical matching;
- document ranking;
- metadata filtering.

## 2.2 Semantic retrieval

Add pgvector.

Learn and expose:

- embeddings;
- vector representation;
- similarity search;
- cosine distance or equivalent similarity functions;
- embedding storage;
- nearest-neighbor retrieval.

## 2.3 Hybrid retrieval

Combine lexical and semantic retrieval.

Possible approaches include:

- normalized score combination;
- reciprocal-rank fusion;
- metadata-aware ranking.

Do not immediately add advanced retrieval techniques.

First measure the baseline.

Only introduce techniques such as:

- query rewriting;
- reranking;
- metadata filtering;
- chunking changes;

when evaluation shows a concrete weakness.

The retrieval implementation should remain visible in project code rather than being hidden entirely behind a high-level framework.

---

# PHASE 3 — EVALUATION

Create a deterministic benchmark based on synthetic incidents.

Each benchmark incident should ideally contain known ground truth:

- actual root cause;
- affected services;
- expected evidence;
- relevant documents;
- expected remediation.

Possible incident classes include:

```text
INC-001  Database connection exhaustion
INC-002  Expired authentication certificate
INC-003  Redis memory eviction
INC-004  Incorrect deployment configuration
INC-005  N+1 query regression
INC-006  External API timeout
INC-007  Kafka consumer lag
INC-008  Incorrect environment variable
```

## Evaluation metrics

Possible metrics include:

- retrieval Recall@K;
- root-cause accuracy;
- evidence precision;
- unsupported-claim rate;
- investigation latency;
- token usage;
- estimated model cost.

Example comparison:

```text
Vector retrieval only                63% root-cause accuracy
Hybrid lexical + vector              72%
Hybrid + query rewriting             76%
Hybrid + reranker                    82%
Hybrid + operational evidence        87%
```

The exact numbers must come from real project evaluations.

Do not claim that a technique improves the system unless the benchmark demonstrates it.

Evaluation should be treated as a first-class engineering component rather than an optional final step.

---

# PHASE 4 — USER INTERFACE

Add a small Next.js + TypeScript frontend.

The frontend is not intended to demonstrate sophisticated frontend architecture.

Its main purpose is to make an investigation understandable to a reviewer.

The interface should show:

- incident details;
- investigation progress;
- evidence collected;
- major tool calls or investigation steps;
- generated hypotheses;
- final diagnosis;
- confidence;
- source attribution;
- proposed remediation;
- approval controls for consequential operations.

Example:

```text
INC-027 — Payment failures

Status: Investigating

Timeline
────────────────────────────
10:31 Deployment detected
10:37 Error rate spike
10:38 Database latency spike
10:40 Relevant configuration identified
10:42 Hypothesis generated
10:43 Evidence verified

Probable cause
Connection pool reduced from 20 → 5

Confidence
87%

Evidence
[logs] [metrics] [deployment] [runbook]

Suggested remediation
Revert configuration change

                    [Approve]
```

Prefer simple React state.

Do not introduce Redux or another global state framework unless a real state-management problem appears.

---

# PHASE 5 — OBSERVABILITY

Introduce observability only once ResolveAI performs meaningful multi-step investigations.

## 5.1 Tracing

Use OpenTelemetry to trace investigation execution.

Possible spans:

```text
investigation
   │
   ├── retrieve_documents
   ├── query_metrics
   ├── inspect_logs
   ├── inspect_deployment
   ├── generate_hypothesis
   └── verify_evidence
```

Tracing should make it possible to see where time is spent inside a single investigation.

## 5.2 Metrics

Expose useful Prometheus metrics such as:

```text
resolve_investigations_total
resolve_investigation_duration_seconds
resolve_tool_calls_total
resolve_tool_failures_total
resolve_retrieval_duration_seconds
resolve_llm_tokens_total
resolve_llm_cost_dollars
```

## 5.3 Grafana

Add Grafana only after meaningful metrics exist.

Possible dashboards:

- investigation volume;
- latency;
- failures;
- model usage;
- estimated cost;
- retrieval performance.

This phase should explicitly reinforce the difference between:

- logs;
- metrics;
- traces.

---

# PHASE 6 — PRODUCTIONIZATION

Productionization and the next capability phases should be implemented as
separate learning steps.

Each step answers a different engineering question.

```text
6.1 Docker
    Containerize the application
    ↓

6.2 CI
    GitHub Actions
    ├── lint
    ├── tests
    └── build
    ↓

6.3 Public Portfolio Deployment
    Northflank Sandbox
    ├── PostgreSQL + pgvector
    ├── private FastAPI
    ├── public Next.js
    └── environment/secrets
    ↓

7 Runtime Data and Generalized Investigations
    user-created incidents, evidence, and knowledge
    ↓

8 External Integration and Demo Hardening
    one read-only integration and controlled real-model demonstration

Optional infrastructure expansion
    AWS ECS/Fargate + Terraform
```

---

## 6.1 Docker — Packaging the Application

### Question answered

> How do I package the application so it runs consistently across environments?

Containerize the application only after the local system is stable.

The objective is to understand:

- images;
- containers;
- Dockerfiles;
- build context;
- layers;
- environment variables;
- networking;
- volumes where appropriate;
- multi-container local development.

When multiple runtime services are involved, use Docker Compose to provide a reproducible local environment.

Possible local services may include:

```text
FastAPI
PostgreSQL
Next.js
Prometheus
Grafana
```

Do not optimize the Docker configuration prematurely.

Start with a readable Dockerfile and improve it only when there is a measurable reason such as:

- build size;
- security;
- cache efficiency;
- startup behavior.

---

## 6.2 CI — Automatically Verifying the Application

### Question answered

> How do I automatically verify that every change still produces a valid application?

Use GitHub Actions.

Begin with a small pipeline:

```text
push / pull request
        ↓
lint
        ↓
tests
        ↓
build
```

Possible later additions:

- type checking;
- integration tests;
- evaluation regression tests;
- Docker image publishing.

The pipeline should grow only when the corresponding checks already exist locally.

CI should automate known engineering practices rather than create new complexity by itself.

---

## 6.3 Public Portfolio Deployment — Northflank Sandbox

### Question answered

> Can somebody open ResolveAI from the Internet and run the proven application
> without the developer machine?

ResolveAI is a hobby and portfolio project, so this milestone requires zero
ongoing hosting cost. Northflank Sandbox matches the proven Compose topology
with two services and one PostgreSQL addon while preserving the existing Docker
packaging.

```text
browser
   ↓ public HTTPS
Northflank Next.js
   ↓ private HTTP
Northflank FastAPI
   ↓ private PostgreSQL
Northflank PostgreSQL + pgvector
```

Only the Next.js service should be public. The browser continues to call
same-origin `/api` paths, and the Next.js server rewrites them to
`http://api:8000` over Northflank's private project network. FastAPI receives the
database connection through a runtime secret named `DATABASE_URL`.

Implement the deployment in independently verified slices:

```text
6.3.1 Sandbox confirmation
6.3.2 PostgreSQL, pgvector, runbooks, and embeddings
6.3.3 private FastAPI and resource-fit verification
6.3.4 public Next.js and end-to-end verification
```

Phases 6.3.1 through 6.3.4 are complete. The private database contains all nine
runbooks and stored embeddings. The private API builds from the root Dockerfile,
uses the deterministic fake, and successfully completes cold and warm
investigations. Its 512 MiB service measured an approximately 440 MiB cold peak
and 320 MiB warm steady state without an OOM or restart.

The public Next.js service is available over HTTPS. Browser-level Chromium
verification rendered all three incidents, completed the diagnosed `INC-001`
and inconclusive `INC-003` reviewer paths, preserved the visual distinction
between collected Evidence, supporting Evidence, and retrieved knowledge, and
observed only same-origin HTTP 200 `/api` responses. There were no failed
requests, page errors, material console errors, or material rendering problems.
Phase 6 productionization and the local Phase 7.1 implementation are complete.
Phase 7.2 is next; Phase 7.1 has not yet been deployed to Northflank.

The Sandbox is a demonstration environment, not a production SLA. Document
limited capacity and model initialization truthfully. Do not add paid compute,
keep-alive requests, fake progress, or additional proxy services to conceal free
tier constraints.

---

## Phase 7 — Runtime Generality and Investigation Provenance

Deployment makes the current frozen synthetic system accessible; it does not
prove that ResolveAI can investigate information the author did not prepare. The
highest-value next phase is therefore runtime generality, not additional
infrastructure.

The current `IncidentContext` naturally describes the fixture collector boundary:
an `Incident` plus raw logs and deployments. It should not become the public
general-purpose import contract. Introduce a small runtime input whose essential
shape is an `Incident` plus normalized `Evidence[]`. The benchmark can adapt its
existing contexts through `inspect_logs()` and `inspect_deployments()`; runtime
input can validate and normalize submitted observations. Keep runtime transport
models distinct from frozen evaluation fixture representations.

The current closed `RootCauseLabel` and evidence enums are useful benchmark
taxonomies. Arbitrary runtime diagnosis must eventually allow causes outside
those six prepared labels and tolerate new evidence descriptions without
weakening benchmark comparability.

### 7.1 Versioned runtime incident input

#### Question answered

> Can ResolveAI investigate an incident that was not created in a Python fixture?

#### Minimal implementation

Accept a strictly validated, versioned JSON bundle containing one incident and a
bounded list of normalized Evidence. Add one small own-data form or import path.
Process the bundle transiently through the existing sequential workflow; do not
add accounts, durable storage, file uploads, or generic CRUD yet.

#### Success criterion

A reviewer can submit a valid external bundle with novel IDs and content, receive
a structured diagnosed or honestly inconclusive result, and no evaluation fixture
or benchmark hash changes.

#### New architectural pressure

The evidence-only fake recognizes two explicit patterns and the six-label output
taxonomy is benchmark-shaped. Unseen input will expose the need for a general
runtime reasoner and runtime-specific diagnosis contract.

Implementation status: complete locally. The bounded version-1 DTO, transient
API endpoint, shared `Incident + Evidence[]` orchestration, minimal Runtime JSON
UI, deterministic diagnosed/inconclusive coverage, and Docker-backed browser
verification pass. The Northflank deployment remains on the Phase 6 build.

### 7.2 Controlled real-model runtime reasoning

#### Question answered

> Can the public runtime reason about previously unseen evidence rather than only
> replaying deterministic fixture rules?

#### Minimal implementation

Use one fixed provider/model selected on the server. Keep credentials off the
browser. Record the provider, model, prompt/schema version, latency, and outcome.
Apply a global daily budget, per-client request limit, concurrency limit, input
limits, provider timeout, and explicit provider-error response. Do not offer a
model picker and do not silently fall back to the deterministic fake.

The deterministic fake remains required for tests, CI, local deterministic
development, baseline evaluation, and a clearly labeled guided public demo.

#### Success criterion

One novel incident outside the fake's two programmed patterns receives a grounded
structured diagnosis or a truthful inconclusive result from the disclosed real
model without exposing credentials or permitting unlimited cost.

#### New architectural pressure

Provider nondeterminism, availability, latency, cost, and broader output language
will require runtime-specific evaluation and honest failure presentation.

### 7.3 Scoped runtime knowledge ingestion

#### Question answered

> Can ResolveAI retrieve useful knowledge supplied for the current runtime
> investigation without contaminating the frozen corpus?

#### Minimal implementation

Introduce `KnowledgeDocument` alongside, not as an immediate replacement for,
the benchmark `Runbook`. Accept a small bounded text or Markdown document set,
validate it, store it under an explicit short-lived runtime scope, generate one
FastEmbed embedding per whole document synchronously, and reuse
PostgreSQL/pgvector Top-3 retrieval. The operation should succeed atomically or
report embedding failure; partially ready documents must not appear in retrieval.

Do not add chunking, queues, workers, hybrid retrieval, reranking, query rewriting,
or a dedicated vector database until document size or evaluation demonstrates a
concrete limitation.

#### Success criterion

A novel incident retrieves an unseen user-supplied document that materially
supports the investigation, while running the frozen benchmark before and after
produces the same corpus and expected inputs.

#### New architectural pressure

User-generated corpora introduce scope, ownership, duplicates, stale documents,
embedding-model version consistency, deletion, and eventual re-embedding
questions before they create a ranking-algorithm problem.

### 7.4 Runtime evaluation slice

#### Question answered

> Does runtime ingestion work beyond one successful demonstration, and does it
> fail safely when evidence or knowledge is insufficient?

#### Minimal implementation

Create a separate frozen set of imported runtime bundles covering retrieval,
citation validity, abstention, malformed input, and corpus isolation. Measure the
existing semantic baseline before changing retrieval. Keep the original ten-case
investigation benchmark and retrieval cases unchanged.

#### Success criterion

The runtime bundle suite is repeatable, reports explicit retrieval/reasoning
outcomes, and proves that mutable runtime documents cannot enter evaluation
queries.

#### New architectural pressure

Measured failures may justify metadata filters, document chunking, deduplication,
or a retrieval experiment. Those changes should follow evidence, not precede it.

### 7.5 Minimal investigation provenance

#### Question answered

> Is retaining an investigation materially useful for comparison and
> explainability rather than merely adding CRUD?

#### Minimal implementation

Persist an immutable `InvestigationRun` snapshot only after transient runtime use
is proven. Retain the incident input, normalized Evidence, retrieved document IDs
and scores, citations, diagnosis or failure, reasoner/model metadata, timestamps,
and latency. Use concrete storage functions; do not introduce a generic
`Repository[T]` or DAO framework. Start with short-lived anonymous retention and
an unguessable capability identifier plus explicit deletion.

Persist `Incident` and `Evidence` as first-class rows only when editing, reuse, or
multiple runs makes that normalization useful. Keep Evidence as the observed-fact
boundary and retrieved knowledge as a separate reference boundary.

#### Success criterion

A reviewer can compare two runs for one submitted incident and see exactly which
observations, retrieved knowledge, citations, reasoner, latency, and outcome
changed.

#### New architectural pressure

Durable private history, cross-device access, or private knowledge would finally
justify authentication and stronger retention/deletion controls. Until then,
accounts and multi-user workspaces are unnecessary.

---

## Phase 8 — One External Source and Demo Hardening

### 8.1 Read-only GitHub knowledge import

#### Question answered

> Can ResolveAI acquire useful operational context from one real external system
> through a bounded, auditable integration?

#### Minimal implementation

After generic document ingestion works, import selected Markdown documentation
from one public GitHub repository at an explicit commit SHA. Preserve repository,
path, and commit provenance. Do not add OAuth, private repositories, broad
crawling, webhooks, autonomous code inspection, or multiple integrations.

#### Success criterion

A selected document is imported with commit provenance, embedded through the same
runtime knowledge path, retrieved for a relevant incident, and removable without
affecting the benchmark.

#### New architectural pressure

Private repositories, refresh, permissions, and moving branches would introduce
authentication and synchronization complexity. They remain separate decisions.

### 8.2 Reviewer journey and public-demo hardening

#### Question answered

> Can a reviewer quickly understand both the controlled benchmark and the proof
> of runtime generality?

#### Minimal implementation

Present two clear paths: a prepared deterministic guided demo and an own-data
investigation using the fixed real reasoner. Label the reasoner and data source,
show truthful loading/provider/limit errors, and add one browser end-to-end test
for each critical path.

Apply minimum hobby-demo safeguards: schema versioning, strict request/document
counts and text sizes, UTF-8 and supported-type validation, duplicate-ID and
timestamp checks, rate/concurrency/model-budget limits, no request-body logging,
explicit retention/deletion behavior, and untrusted-document prompt boundaries.
Do not fetch arbitrary URLs or expose shell, SQL, mutating, or unrestricted tools.

#### Success criterion

A new reviewer can complete the guided flow, investigate one valid unseen bundle,
understand which path is deterministic versus model-generated, and receive clear
feedback for a limit or provider failure.

#### New architectural pressure

Only demonstrated reviewer confusion, abuse, or durability needs should motivate
larger UI, authentication, background processing, or operational controls.

### Expansion prioritization

These classifications describe the next major product phase, not permanent bans:

| Capability | Priority now | Reason |
|---|---|---|
| Runtime user-created incidents | High-value next step | Directly proves the system can accept previously unseen input. |
| Persistent incidents and Evidence | Useful later | Justified by reuse, editing, or multiple runs, not by the first transient proof. |
| Persistent investigation history | Useful later | Strengthens provenance once real runtime investigations exist. |
| Generic `KnowledgeDocument` ingestion | High-value next step | Proves retrieval over user-supplied context rather than only nine authored runbooks. |
| JSON incident bundle import | High-value next step | Smallest portable generalization seam and easier to validate than many integrations. |
| `.log`, `.txt`, `.md`, and `.json` uploads | Useful later | Helpful after the normalized bundle/text path is stable; each parser expands the attack and validation surface. |
| Real LLM reasoning in the public demo | High-value next step | The fake is an excellent deterministic test double but undersells runtime AI capability. |
| Read-only GitHub integration | Useful later | High portfolio value only after the generic ingestion boundary exists. |
| Authentication | Probably unnecessary | Transient or short-lived anonymous use does not justify SaaS account machinery. |
| Multi-user workspaces | Actively harmful / overengineering | Adds tenancy complexity without strengthening the investigation story. |
| Background embedding jobs | Probably unnecessary | Small bounded documents can be embedded synchronously and atomically. |
| LangGraph or agentic investigation | Actively harmful / overengineering | The current sequential workflow has no justified branching/tool loop requirement. |
| External observability integrations | Probably unnecessary | Generic input and one GitHub source have a better value-to-complexity ratio first. |
| AWS/ECS deployment | Probably unnecessary | Northflank already answers the public-access question at the required cost. |
| Terraform | Probably unnecessary | Infrastructure-as-code would currently describe optional infrastructure rather than solve a product limitation. |
| Browser end-to-end tests | Useful later | One critical test per public path becomes valuable once the own-data path exists. |
| Additional retrieval techniques | Probably unnecessary | Scope isolation and new evaluation must reveal a ranking limitation first. |
| Additional model benchmarking | Useful later | Valuable after the generalized runtime contract and real-model baseline stabilize. |

Do not build the next phase around a CRUD administration surface, accounts,
workspaces, multiple integrations, queues, background workers, chunking, provider
routing, silent model fallback, autonomous tools, remediation execution, a generic
repository layer, or AWS for its own sake. Those additions would increase the
technology list faster than they increase evidence of AI engineering capability.

From a portfolio-review perspective, the capabilities that materially change the
project are: accepting unseen incident data, reasoning beyond two hand-coded
patterns, retrieving user-supplied knowledge without corpus leakage, evaluating
that generalized path, and preserving inspectable provenance. One restrained
GitHub import then demonstrates a real boundary. Additional cloud brands,
frameworks, integrations, or SaaS boilerplate would mostly add nouns to the
README unless a measured limitation first makes them necessary.

---

## Optional infrastructure expansion — AWS and Terraform

AWS ECS/Fargate and Terraform remain useful portfolio exercises for container
orchestration and infrastructure as code. They are optional because the current
project's primary value is its AI engineering architecture and its immediate
hosting constraint is zero ongoing cost.

If pursued later, first understand and manually prove the AWS architecture, then
encode it with Terraform. The optional exercise may cover:

- ECR image storage;
- ECS task and service behavior;
- Fargate compute;
- environment and secret delivery;
- Terraform resources, variables, outputs, state, plan, and apply.

A useful mental model is:

```text
manual understanding
        ↓
working AWS architecture
        ↓
Terraform representation
        ↓
reproducible infrastructure
```

Do not create Terraform modules merely for architectural appearance. Extract
modules only when repetition or reuse creates a concrete need.

---

# 5. Why These Infrastructure Choices?

## FastAPI

FastAPI provides a simple Python boundary between the investigation engine and external clients.

It is preferred because:

- the project is primarily Python-based;
- Pydantic integrates naturally with structured AI output;
- endpoints remain easy to understand;
- the domain logic can remain independent from the HTTP layer.

FastAPI should expose the application, not contain the application's core business logic.

Prefer:

```python
result = investigate_incident(incident)
```

with FastAPI calling this logic rather than embedding investigation logic directly inside route handlers.

---

# PostgreSQL + pgvector

PostgreSQL is deliberately preferred over immediately introducing several specialized databases.

The same system can initially support:

- application data;
- incidents;
- documents;
- metadata;
- lexical search;
- embeddings.

This minimizes operational complexity and exposes the retrieval concepts clearly.

Instead of beginning with:

```text
PostgreSQL
Pinecone
Elasticsearch
Redis
```

ResolveAI can begin with:

```text
PostgreSQL
├── relational data
├── full-text search
└── pgvector
```

A dedicated vector database or search engine can later be introduced only if the project identifies a concrete limitation.

---

# LangGraph

LangGraph is appropriate only if the investigation workflow eventually contains meaningful graph behavior such as:

- branching;
- retries;
- loops;
- stateful investigation;
- conditional evidence gathering.

The initial workflow should preferably use plain Python.

For example:

```text
collect_context()
      ↓
inspect_logs()
      ↓
generate_hypothesis()
      ↓
verify_evidence()
      ↓
build_diagnosis()
```

If this later evolves into:

```text
generate hypothesis
      ↓
enough evidence?
   ↙          ↘
 no            yes
 ↓              ↓
collect more   diagnose
evidence
 ↓
repeat
```

then a workflow framework becomes easier to justify.

---

# Next.js

The frontend exists because a portfolio project benefits from a visual interface that makes the investigation process understandable.

Next.js + TypeScript provides:

- a modern frontend stack;
- a useful way to display investigation state;
- a clear separation between frontend and API;
- additional experience with typed web development.

The frontend should remain deliberately small.

---

# OpenTelemetry

Prometheus can tell us that an investigation took several seconds.

OpenTelemetry can show where that time was spent.

For example:

```text
investigation                3.7 s
├── retrieval                0.4 s
├── inspect_logs             0.2 s
├── hypothesis_generation    1.8 s
└── verification             1.1 s
```

This becomes valuable once a single request contains several internal operations.

---

# Prometheus + Grafana

Prometheus records operational metrics.

Grafana visualizes those metrics.

They should demonstrate actual operational questions such as:

- How long do investigations take?
- Which tools fail most often?
- How many tokens are used?
- Which model is more expensive?
- Is retrieval slowing down?

They should not exist merely so the README can list Prometheus and Grafana.

---

# Docker

Docker answers:

> How do I package the application?

It creates a reproducible runtime artifact.

Docker Compose now reproduces the local PostgreSQL, FastAPI, and Next.js
multi-service environment implemented in Phase 6.1.

---

# GitHub Actions

GitHub Actions answers:

> How do I automatically verify/build the application whenever the repository changes?

It is preferred here over Jenkins because the project is intended to be a public GitHub portfolio repository and Jenkins has already been demonstrated elsewhere.

---

# Optional AWS ECS + Fargate

ECS answers:

> How do I run and manage my application containers?

Fargate removes the need to provision and maintain EC2 container hosts. It is an
optional future infrastructure exercise rather than the current deployment
requirement.

This allows the project to focus first on:

- container deployment;
- configuration;
- task definitions;
- service lifecycle;
- image delivery;

without adding server administration.

---

# Optional ECR

ECR answers:

> Where does the Docker image live after CI builds it?

It connects the packaging and deployment stages:

```text
GitHub
   ↓
Docker image
   ↓
ECR
   ↓
ECS/Fargate
```

---

# Optional Terraform

Terraform answers:

> How can another environment reproduce the infrastructure I created?

It should describe infrastructure that is already conceptually understood.

Terraform should therefore follow a manually understood AWS architecture if the
optional infrastructure expansion is pursued.

---

# 6. Human-in-the-Loop Safety

ResolveAI may eventually recommend corrective actions.

Read-only operations may become autonomous.

Mutating operations must require explicit human approval.

Example:

```text
investigate
    ↓
identify remediation
    ↓
generate proposed change
    ↓
run validation/tests
    ↓
show diff
    ↓
human approval
    ↓
perform approved action
```

The system must not allow an LLM to:

- execute unrestricted shell commands;
- run arbitrary SQL;
- modify production systems without approval;
- access capabilities outside narrowly defined tools.

---

# 7. Suggested Repository Structure

The structure should remain modest initially and grow with the phases.

A possible long-term shape is:

```text
resolve-ai/
│
├── apps/
│   ├── api/
│   └── web/
│
├── resolve_ai/
│   ├── investigation/
│   ├── retrieval/
│   ├── models/
│   ├── evaluation/
│   └── observability/
│
├── datasets/
│   ├── incidents/
│   ├── runbooks/
│   └── documentation/
│
├── evals/
│
├── tests/
│
├── docs/
│   └── adr/
│
├── infrastructure/
│   ├── docker/
│   └── terraform/
│
└── .github/
    └── workflows/
```

Do not create empty directories for future architecture merely to make the repository look complete.

Create structure when code actually needs it.

---

# 8. Architecture Decision Records

Maintain lightweight ADRs in:

```text
docs/adr/
```

Useful decisions may include:

- modular monolith before microservices;
- PostgreSQL + pgvector instead of a dedicated vector database;
- lexical + vector hybrid retrieval;
- plain Python workflow before LangGraph;
- human approval for mutating tools;
- ECS/Fargate instead of manually managed EC2 hosts.

Each ADR should contain:

```text
Context
Decision
Alternatives considered
Consequences
```

Keep them short.

---

# 9. Testing Strategy

Use:

- unit tests for deterministic domain logic;
- integration tests at infrastructure boundaries;
- evaluation tests for AI behavior;
- end-to-end tests only for important application flows.

Prefer tests that describe observable behavior.

Example:

```python
def test_investigation_identifies_connection_pool_exhaustion(): ...
```

Avoid tests that are excessively coupled to internal implementation details.

For LLM-dependent behavior, separate deterministic application logic from nondeterministic model behavior whenever practical.

---

# 10. Definition of Success

The final project should not merely demonstrate that an LLM can answer questions.

It should demonstrate that its author understands:

- software architecture;
- API design;
- structured AI outputs;
- retrieval;
- embeddings;
- hybrid search;
- evaluation;
- tool use;
- model uncertainty;
- human approval;
- testing;
- observability;
- containers;
- CI;
- cloud deployment;
- infrastructure as code.

The most important success criterion is:

> I should be able to open any important file in the repository and explain why it exists, what enters it, what it produces, what it depends on, why the implementation was chosen, and what its limitations are.

The objective is not to demonstrate how much code an AI coding agent can generate.

The objective is to build a production-oriented AI system whose architecture I understand and can defend.
