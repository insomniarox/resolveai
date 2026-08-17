# File Purpose
│  How should Codex approach development?
│  Keep code pedagogical
│  Don't over-engineer
│  Explain architectural changes
│  Work incrementally
│  Respect phases

# ResolveAI — Codex Development Instructions

Read `PROJECT.md` completely before making any changes.

`PROJECT.md` describes the long-term vision of ResolveAI.

Do **not** interpret it as an instruction to implement the entire architecture immediately.

This project has two equally important goals:

1. Build a credible production-oriented AI engineering portfolio project.
2. Help me learn software architecture and AI engineering while building it.

The second goal is a hard requirement.

---

# 1. Core Development Principle

The code must remain simple, readable, explicit, and understandable.

I am learning while building this project.

I need to eventually be able to explain the important parts of the codebase myself during a technical interview.

Therefore:

- code has to be commented;
- prefer straightforward code over clever code;
- prefer explicit control flow over hidden framework behavior;
- prefer small functions with descriptive names;
- prefer simple Python classes and Pydantic models;
- use type hints;
- avoid premature abstraction;
- avoid unnecessary design patterns;
- avoid abstraction layers that currently have only hypothetical value;
- avoid generic factories, managers, registries, adapters, repositories, or dependency-injection machinery unless a concrete requirement justifies them;
- avoid deeply nested inheritance;
- prefer composition over inheritance;
- do not create interfaces merely because an enterprise codebase might have them;
- do not split a simple operation across many files;
- do not add a dependency when a small amount of clear code would be easier to understand;
- do not use framework features when plain Python communicates the idea better.

A useful rule is:

> Start concrete. Introduce abstraction when the code demonstrates why the abstraction is needed.

Architecture should emerge from requirements rather than from trying to make the repository look sophisticated.

---

# 2. Teaching Requirement

Before implementing a substantial architectural change, explain:

1. what problem we are solving;
2. the simplest possible solution;
3. the solution you recommend;
4. why the additional complexity is justified;
5. what alternatives exist;
6. what trade-offs we are accepting.

Keep these explanations concise and concrete.

When introducing an unfamiliar concept, explain it using the code in this repository rather than only giving an abstract definition.

Examples:

If introducing dependency inversion:

> Explain which concrete dependency in ResolveAI motivates it.

If introducing LangGraph:

> First explain what workflow problem plain Python is becoming awkward at solving.

If introducing pgvector:

> Explain what data is being embedded, how similarity search works conceptually, and what database operation is being performed.

If introducing Docker:

> Explain what inconsistency or packaging problem the container solves.

If introducing Terraform:

> Explain which AWS resources already exist conceptually and why reproducing them manually is now undesirable.

---

# 3. Understanding Gate

Do not make very large architectural changes in a single step.

Break work into changes small enough that I can inspect and understand them.

After implementing an important subsystem, provide:

## What changed

A short description of the implementation.

## Why it exists

What concrete requirement caused this code to exist.

## How it works

Explain the execution flow using actual files, classes, and functions from the repository.

## What to study

Identify the 2–4 concepts demonstrated by the implementation.

## Trade-offs

Explain:

- what is deliberately simplified;
- what limitations currently exist;
- what would likely change in a larger production system.

---

# 4. Development Strategy

Build ResolveAI incrementally.

Do not implement later phases until the current phase has a coherent working version.

The development sequence defined in `PROJECT.md` is:

```text
PHASE 1 — Investigation Core
PHASE 2 — Retrieval
PHASE 3 — Evaluation
PHASE 4 — User Interface
PHASE 5 — Observability
PHASE 6 — Productionization
```

The remaining roadmap is organized as:

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

7 Runtime Generality and Investigation Provenance
    7.1 versioned runtime incident input
    7.2 controlled real-model runtime reasoning
    7.3 scoped runtime knowledge ingestion
    7.4 runtime evaluation slice
    7.5 minimal investigation provenance
    ↓

8 One External Source and Demo Hardening
    8.1 read-only GitHub knowledge import
    8.2 dual-path reviewer experience and safety boundaries

Optional infrastructure expansion
    AWS ECS/Fargate + Terraform
```

These steps must remain separate.

Do not collapse them into one large "deployment" task.

---

# PHASE 1 — INVESTIGATION CORE

Build the smallest useful version of ResolveAI.

Initial goals:

- Python application;
- FastAPI API;
- synthetic incidents;
- synthetic logs;
- synthetic deployment history;
- simple investigation workflow;
- structured Pydantic outputs;
- deterministic fake implementations where useful;
- unit tests.

At this stage:

- no cloud infrastructure;
- no Terraform;
- no Kubernetes;
- no Prometheus;
- no Grafana;
- no distributed microservices;
- no message broker;
- no vector database unless retrieval is explicitly being implemented;
- no frontend unless needed to understand or exercise the API.

The application should first prove that one incident can be investigated end-to-end.

Prefer ordinary Python orchestration initially.

Do not introduce LangGraph automatically.

---

# PHASE 2 — RETRIEVAL

Add a knowledge base containing synthetic:

- runbooks;
- previous incidents;
- architecture documentation;
- service documentation.

Use PostgreSQL.

Begin with PostgreSQL full-text search for lexical retrieval.

Then add pgvector for semantic retrieval.

The implementation should make it possible for me to understand:

- document chunking;
- embeddings;
- vector similarity;
- lexical search;
- ranking;
- hybrid retrieval.

Do not hide the complete retrieval system behind LangChain convenience APIs.

Libraries may be used for embeddings and model access, but the retrieval and ranking flow should remain visible in project code.

Start with the simplest retrieval baseline.

Measure it.

Only introduce techniques such as:

- query rewriting;
- reranking;
- reciprocal-rank fusion;
- metadata filtering;
- alternative chunking;

when evaluation demonstrates a concrete problem.

---

# PHASE 3 — EVALUATION

Create a deterministic synthetic incident benchmark.

Each benchmark incident should contain ground truth where practical:

- actual root cause;
- relevant services;
- expected evidence;
- relevant documents;
- expected remediation.

Create an evaluation harness capable of measuring useful metrics such as:

- retrieval recall;
- root-cause accuracy;
- evidence precision;
- unsupported claims;
- latency;
- token usage;
- estimated model cost.

Evaluation code is a first-class part of the project.

Do not claim that an architectural technique improves ResolveAI unless an evaluation demonstrates the improvement.

Prefer simple, transparent evaluation logic before introducing an evaluation framework.

---

# PHASE 4 — USER INTERFACE

Add a small Next.js + TypeScript frontend.

The objective is not advanced frontend engineering.

The objective is to make an investigation easy to understand visually.

The interface should display:

- incident information;
- investigation progress;
- major investigation steps;
- evidence;
- hypotheses;
- final diagnosis;
- confidence;
- source attribution;
- proposed remediation;
- human approval where a mutating operation would occur.

Keep frontend state management simple.

Do not introduce Redux or another global-state framework unless the application demonstrates a real need.

---

# PHASE 5 — OBSERVABILITY

Once the application performs meaningful multi-step investigations, introduce observability.

Use OpenTelemetry to trace execution.

Possible trace operations include:

- retrieval;
- tool calls;
- LLM calls;
- hypothesis generation;
- evidence verification.

Then add useful application metrics with Prometheus.

Possible metrics include:

- investigation count;
- investigation latency;
- tool failures;
- retrieval latency;
- LLM tokens;
- estimated LLM cost;
- model failures.

Use Grafana only after meaningful metrics exist.

When implementing this phase, explain clearly the difference between:

- logs;
- metrics;
- traces.

---

# PHASE 6 — PRODUCTIONIZATION

Productionization must remain incremental.

Each subsection answers a different engineering question.

Do not implement all of Phase 6 at once.

---

## 6.1 Docker

### Learning question

> How do I package the application?

Containerize the application only after the local application is working reliably.

Before implementing Docker:

1. identify which process or services actually need containers;
2. explain what Docker solves for this project;
3. propose the simplest Dockerfile;
4. explain the build and runtime flow.

Start simple.

Do not immediately introduce:

- multi-stage builds;
- distroless images;
- complex entrypoint scripts;
- elaborate health-check systems;
- advanced image-hardening techniques;

unless a concrete requirement justifies them.

If multiple local services exist, Docker Compose may be introduced.

Explain:

- images;
- containers;
- ports;
- environment variables;
- volumes where applicable;
- container networking.

The goal is understanding before optimization.

---

## 6.2 CI — GitHub Actions

### Learning question

> How do I automatically verify and build the application?

Introduce GitHub Actions only after the corresponding commands already work locally.

Begin with:

```text
push / pull request
        ↓
lint
        ↓
tests
        ↓
build
```

Do not create a large CI/CD workflow immediately.

Possible later additions include:

- type checking;
- integration tests;
- evaluation regression tests;
- Docker image publishing.

For every CI step, explain:

> What local command are we automating?

CI should automate existing engineering discipline, not conceal it.

---

## 6.3 Public Portfolio Deployment — Northflank Sandbox

### Learning question

> Can somebody open ResolveAI from the Internet and run the existing application
> without the developer machine?

ResolveAI is currently a hobby and portfolio project with a zero ongoing hosting
cost requirement. Deploy the proven containers to one Northflank Sandbox project:

```text
browser
   ↓ public HTTPS
Next.js service :3000
   ↓ private HTTP
FastAPI service :8000
   ↓ private PostgreSQL
PostgreSQL addon + pgvector
```

Preserve the existing Dockerfiles and Compose environment. Northflank deployment
does not invalidate them: Docker answers whether each runtime can be packaged
reproducibly, while Northflank answers how to expose the application with the
least deployment-specific complexity.

Deploy in separate slices:

1. confirm the Sandbox resource allowance;
2. initialize PostgreSQL, pgvector, schema, runbooks, and stored embeddings;
3. deploy private FastAPI and verify cold/warm resource fit;
4. deploy public Next.js and verify the full same-origin request path.

Phases 6.3.1 through 6.3.4 are complete. The private database contains nine
runbooks with nine stored embeddings. The private FastAPI service successfully
completed cold and warm deterministic investigations. Its 512 MiB allocation
measured approximately 440 MiB at cold FastEmbed initialization and 320 MiB in
the warm steady state without an OOM or restart.

The public web service was built with:

```text
RESOLVEAI_API_URL=http://api:8000
```

Keep FastAPI and PostgreSQL private. The browser must communicate only with the
public Next.js origin; no FastAPI CORS change is required for that architecture.

Browser-level Chromium verification confirmed that all three incidents render,
`INC-001` completes with its diagnosed presentation, `INC-003` completes with
its successful inconclusive presentation, and collected Evidence, cited
supporting Evidence, and RetrievedRunbooks remain visually distinct. The browser
observed same-origin HTTP 200 `/api` responses and no failed requests, page
errors, material console errors, or material rendering problems. Phase 6 is
complete. Phase 7.1 is complete locally but is not yet deployed to Northflank.
Phase 7.2 is next and has not started.

Use the database addon's standard application URI as `DATABASE_URL` through
Northflank runtime secrets. Do not commit database credentials, use the
administrator URI at runtime, or add OpenAI/OpenRouter credentials. The public
demo continues to use the deterministic fake.

Treat Northflank Sandbox as a constrained public demonstration rather than a
production SLA. Document cold model initialization and limited concurrency
truthfully. Do not add keep-alive traffic, fake progress, paid capacity, or an
additional proxy merely to conceal free-tier limitations.

---

## Phase 7 — Runtime Generality and Investigation Provenance

The next product question is whether ResolveAI can investigate data the project
author did not prepare. Preserve two explicit worlds:

```text
ResolveAI
├── evaluation world
│   ├── immutable synthetic fixtures and ground truth
│   ├── frozen retrieval cases and benchmark corpus
│   └── repeatable deterministic/model evaluation
└── runtime world
    ├── user-supplied Incident and Evidence
    ├── scoped KnowledgeDocument data
    ├── controlled real-model reasoning
    └── later: immutable InvestigationRun history
```

Do not convert benchmark fixtures into mutable production rows. Mutable runtime
documents must not enter benchmark retrieval. Keep benchmark hashes, expected
labels, cases, and retrieval inputs unchanged. Share investigation, retrieval,
structured-output, and citation-verification logic only through explicit input
adapters.

The current `IncidentContext` is a good fixture/collector representation, not a
general upload contract. Introduce the smallest runtime input around an
`Incident` and normalized `Evidence[]`. Keep runtime API DTOs distinct from
evaluation fixtures. The closed benchmark root-cause and evidence taxonomies must
not prevent arbitrary runtime descriptions or diagnoses.

### 7.1 Versioned runtime incident input

Answer only:

> Can one previously unseen incident pass through the investigation workflow?

Accept one strictly validated, size-bounded, versioned JSON bundle with an
incident and Evidence. Process it transiently. Add only the minimal own-data UI
needed to submit or paste it. Do not add persistence, accounts, workspaces, a CRUD
dashboard, file uploads, or a generic repository abstraction in this slice.

Stop when a novel bundle returns a structured diagnosed or honestly inconclusive
result and the frozen benchmark remains unchanged.

Status: complete locally. The version-1 DTO, transient endpoint, shared
`Incident + Evidence[]` workflow, Runtime JSON UI, deterministic API coverage,
and Docker-backed browser verification pass. Do not reopen this slice unless a
regression is found or a deliberate Northflank deployment is requested.

### 7.2 Controlled real-model runtime reasoning

Answer only:

> Can the runtime reason beyond the fake's two programmed evidence patterns?

Use one fixed provider/model selected by FastAPI. Keep the provider credential
server-side. Record provider/model and prompt/schema version with each response.
Add strict input, per-client request, concurrency, daily model-budget, timeout,
and provider-error boundaries. Do not expose a model picker and do not silently
fall back to the fake after a real-model error.

The deterministic fake remains required for tests, CI, deterministic development,
baseline evaluation, and the clearly labeled guided public demo. Evaluation may
continue to select supported reasoners separately.

Stop when a novel incident outside the fake patterns produces a grounded real
model result or truthful abstention without exposing credentials or unlimited
cost.

### 7.3 Scoped runtime knowledge ingestion

Answer only:

> Can knowledge supplied at runtime help an investigation without affecting the
> benchmark corpus?

Introduce `KnowledgeDocument` alongside the frozen `Runbook` concept. Start with
small bounded text or Markdown documents, one whole-document embedding,
synchronous FastEmbed generation, an explicit short-lived runtime scope, and the
existing pgvector semantic Top-3 retrieval. Treat embedding and storage as one
operation: a failed embedding must not create a retrievable half-ready document.

Do not add chunking, queues, workers, hybrid retrieval, reranking, query rewriting,
or a dedicated vector database without a measured limitation.

Stop when an unseen scoped document is retrieved usefully for a novel incident
and cannot appear in a benchmark query.

### 7.4 Runtime evaluation slice

Answer only:

> Does generalized ingestion work repeatably, abstain honestly, and preserve
> corpus isolation?

Create a separate frozen set of imported runtime bundles covering successful
retrieval, insufficient evidence, malformed input, citation validity, and scope
isolation. Measure the existing semantic baseline before adding retrieval
techniques. Do not edit the original ten-case benchmark to accommodate runtime
features.

Stop when the runtime suite produces repeatable measurements and proves that
mutable data cannot change frozen evaluation inputs.

### 7.5 Minimal investigation provenance

Answer only:

> Does persisted history strengthen explainability and comparison enough to
> justify durable runtime data?

Only after the transient path is useful, persist immutable `InvestigationRun`
snapshots containing input, normalized Evidence, retrieved document IDs and
scores, citations, diagnosis or failure, reasoner/model metadata, timestamps, and
latency. Preserve the distinction:

```text
observation
≠ retrieved knowledge
≠ model inference
```

Use concrete database access functions. Do not introduce a generic
`Repository[T]`, DAO family, or persistence framework. Normalize `Incident` and
`Evidence` into their own tables only when editing, reuse, or multiple runs makes
that useful. Begin with short-lived anonymous retention, an unguessable capability
identifier, and explicit deletion.

Authentication becomes justified only for durable private history, private
knowledge, cross-device access, or private integrations. Multi-user workspaces are
not a portfolio-demo requirement.

---

## Phase 8 — One External Source and Demo Hardening

### 8.1 Read-only GitHub knowledge import

Add GitHub only after generic knowledge ingestion works. Import explicitly
selected Markdown files from one public repository at a specific commit SHA, and
store repository/path/commit provenance. Reuse the runtime document ingestion
path.

Do not add OAuth, private repositories, recursive crawling, webhooks, autonomous
code browsing, or a second external integration in this phase.

Stop when one selected document can be imported, retrieved, traced to its exact
commit, and removed without affecting evaluation.

### 8.2 Reviewer journey and public-demo hardening

Expose two clearly labeled paths:

```text
Guided demo                         Investigate your own data
prepared synthetic incident        versioned bundle / minimal form
deterministic fake                  fixed server-side real reasoner
repeatable architecture tour       proof of previously unseen input
```

Show truthful loading, provider failure, and usage-limit states. Add one browser
end-to-end test for each critical path rather than broad UI automation.

Minimum safeguards are schema and size limits, document/evidence count limits,
UTF-8 and supported-type validation, duplicate-ID and timestamp checks,
rate/concurrency/model-budget limits, no body logging, explicit retention and
deletion, and treating uploaded knowledge as untrusted prompt content. Do not add
arbitrary URL fetching, HTML execution, shell/SQL access, mutating tools, or
unrestricted agent tools.

Keep the workflow as sequential Python. LangGraph or another graph runtime becomes
justified only when a real requirement introduces conditional evidence gathering,
tool retries, loops, checkpoint/resume, or human pauses that make the current
control flow materially awkward.

---

## Optional infrastructure expansion — AWS ECS/Fargate and Terraform

AWS and Terraform remain useful future learning exercises but are not required
for the current zero-cost portfolio milestone. If pursued, first understand and
manually prove ECR, ECS task/service, Fargate, environment, and secret behavior;
then encode that understood architecture in Terraform.

The desired optional progression is:

```text
understand AWS infrastructure
        ↓
create a working AWS deployment
        ↓
identify manual/repetitive setup
        ↓
describe it in Terraform
```

Before writing Terraform, explain which existing infrastructure will be represented as code.

Teach the concepts progressively:

- provider;
- resource;
- variable;
- output;
- state;
- plan;
- apply;
- resource dependency.

Do not create Terraform modules merely to make the repository look professional.

Extract modules only when:

- repetition exists;
- reuse exists;
- complexity genuinely improves through grouping.

Any future Terraform should reproduce only the AWS infrastructure actually
required by the optional deployment exercise.

---

# 5. Architecture Constraints

Prefer a modular monolith initially.

Do not create microservices merely because the simulated system contains business services such as:

```text
payment-service
account-service
fraud-service
notification-service
```

These may initially exist as:

- datasets;
- fixtures;
- modules;
- simulated external systems.

Split actual services only if doing so teaches or demonstrates a concrete architectural need.

Keep domain logic independent from FastAPI where practical.

Prefer:

```python
result = investigate_incident(incident)
```

where the core operation can be tested independently of HTTP.

FastAPI should expose the application rather than contain the application's business logic.

---

# 6. AI-Specific Principles

LLMs are not reliable deterministic functions.

Where appropriate:

- validate structured output;
- handle malformed responses;
- record model errors;
- preserve evidence used for conclusions;
- distinguish evidence from model inference;
- make unsupported claims measurable;
- require human approval for consequential mutating actions.

Read operations may eventually be autonomous.

Mutating operations must require explicit human approval.

Do not allow an LLM to execute:

- unrestricted shell commands;
- arbitrary SQL;
- unrestricted filesystem mutations;
- uncontrolled cloud actions.

Tool interfaces should expose narrow capabilities.

---

# 7. Model / Provider Abstractions

Do not create a large generic LLM framework.

Start with one provider if that is all we need.

If a second provider or a testing requirement appears, then consider refactoring toward a small shared protocol.

For example:

```python
class ModelProvider(Protocol):
    async def generate(
        self,
        messages: list[Message],
    ) -> ModelResponse: ...
```

Only introduce such an abstraction when at least one of these is true:

- a second concrete provider exists;
- testing requires substitution;
- the current implementation has demonstrated unwanted coupling.

Explain the refactoring when it happens.

---

# 8. Testing Principles

Tests should explain behavior.

Prefer:

```python
def test_investigation_identifies_connection_pool_exhaustion(): ...
```

over tests that merely mirror implementation details.

Use:

- unit tests for deterministic domain logic;
- integration tests at infrastructure boundaries;
- evaluation tests for AI behavior;
- end-to-end tests sparingly for critical flows.

Mocks should be used deliberately.

Prefer deterministic fake implementations when they make behavior easier to understand.

For LLM-dependent behavior, separate deterministic application logic from nondeterministic model behavior whenever possible.

---

# 9. Documentation

Maintain lightweight Architecture Decision Records under:

```text
docs/adr/
```

Only create an ADR for meaningful architectural decisions.

Possible examples:

- PostgreSQL + pgvector instead of a dedicated vector database;
- modular monolith before microservices;
- hybrid lexical/vector retrieval;
- plain Python workflow before LangGraph;
- human approval for mutating tools;
- ECS/Fargate instead of EC2 hosts.

Each ADR should answer:

```text
Context
Decision
Alternatives considered
Consequences
```

Keep ADRs short.

Architecture diagrams should explain the system rather than decorate the repository.

---

# 10. Dependency Rule

Before adding a substantial dependency, state:

> We are adding X because Y.

If Y can reasonably be solved with simple code that is easier to understand, prefer the simpler implementation until its limitations become visible.

---

# 11. Refactoring Rule

Do not refactor because code "could be more extensible."

Refactor when there is an observable problem such as:

- duplicated logic;
- difficult testing;
- unwanted coupling;
- a second implementation;
- changing requirements;
- excessive function or class responsibility.

When refactoring, explain what concrete code smell or requirement motivated it.

A useful narrative should often look like:

```text
We originally had X.

X became inadequate because Y.

Therefore we introduced Z.
```

Examples:

```text
We originally used PostgreSQL full-text search.

Semantically similar incidents using different terminology were frequently missed.

Therefore we introduced embeddings and pgvector.
```

```text
We originally orchestrated the investigation with sequential Python functions.

Conditional evidence gathering introduced loops and branches that became difficult to follow.

Therefore we introduced LangGraph.
```

```text
We originally logged total request duration.

A single investigation later contained multiple retrieval and model operations, and we could not determine where time was being spent.

Therefore we introduced OpenTelemetry tracing.
```

This reasoning is important because I need to be able to explain architectural evolution during interviews.

---

# 12. Code Review Behavior

When I ask you to implement a feature:

- stay within scope;
- do not silently perform broad unrelated refactors;
- inspect the relevant existing code first;
- preserve working behavior unless the task explicitly changes it.

If you notice unrelated architectural problems, mention them separately.

Do not automatically fix everything you notice.

---

# 13. Comments

Do not add comments that merely repeat the code.

Bad:

```python
# Increment counter
counter += 1
```

Useful:

```python
# Reciprocal-rank fusion uses rank rather than raw similarity scores
# because lexical and vector similarity scores are not directly comparable.
```

Comments should explain:

- reasoning;
- constraints;
- non-obvious behavior.

---

# 14. Naming

Names should communicate domain concepts.

Prefer:

```python
retrieve_relevant_runbooks()
calculate_retrieval_recall()
verify_hypothesis()
```

over:

```python
process_data()
handle_result()
run_step()
```

Avoid abbreviations unless they are established terminology.

---

# 15. Most Important Constraint

I should eventually be capable of opening any important file in this repository and explaining:

- why it exists;
- what enters it;
- what it produces;
- what dependencies it has;
- why the implementation was chosen;
- what its limitations are.

If an implementation would make that unnecessarily difficult, choose a simpler implementation.

The objective is not to demonstrate how much code an AI coding agent can generate.

The objective is to build a system whose architecture **I understand and can defend**.
