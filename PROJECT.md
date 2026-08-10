# File Purpose
│  What are we building?
│  Why does it exist?
│  What architecture are we aiming toward?
│  What are the phases?
│  Why were technologies chosen?

# ResolveAI

## AI Incident Investigation Copilot

ResolveAI is a production-oriented AI engineering portfolio project built to investigate synthetic software incidents by combining structured operational data, retrieval, LLM reasoning, evaluation, observability, and eventually cloud deployment.

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

The project should use entirely synthetic data.

No real employer, banking, customer, or confidential production data should be included.

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

Productionization should be implemented as four separate learning steps.

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

6.3 Cloud Deployment
    AWS ECS + Fargate
    ├── ECR
    ├── ECS task
    ├── ECS service
    └── environment/secrets
    ↓

6.4 Infrastructure as Code
    Terraform
    └── reproduce the infrastructure
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

## 6.3 Cloud Deployment — Running the Container

### Question answered

> Where does the packaged application actually run?

Deploy the application to AWS using ECS with Fargate.

### ECR

Use Amazon Elastic Container Registry to store Docker images.

Conceptually:

```text
source code
    ↓
Docker build
    ↓
container image
    ↓
ECR
```

### ECS task

Define how the container should run.

The task definition should describe concepts such as:

- image;
- CPU;
- memory;
- ports;
- environment variables;
- secrets.

### ECS service

Use an ECS service to keep the required application task running.

Learn concepts such as:

- desired task count;
- deployment updates;
- health;
- task replacement.

### Fargate

Use Fargate so that the project can run containers without provisioning or maintaining EC2 hosts.

The learning objective is to understand container deployment before introducing host-management complexity.

### Environment and secrets

Configuration must be separated from application code.

Do not commit credentials.

Learn the difference between:

- ordinary environment configuration;
- sensitive secrets;
- local `.env` files;
- cloud-managed configuration.

Only introduce additional AWS services when the application genuinely requires them.

---

## 6.4 Terraform — Reproducing Infrastructure

### Question answered

> How do I describe and reproduce the deployment infrastructure instead of creating it manually?

Terraform should be introduced **after** the AWS deployment has been understood conceptually.

Terraform is not the first tool used to discover how AWS works.

First understand the infrastructure.

Then encode it.

Terraform should reproduce resources such as those required for the ECS/Fargate deployment.

The objective is to learn:

- declarative infrastructure;
- providers;
- resources;
- variables;
- outputs;
- Terraform state;
- planning;
- applying changes;
- dependency relationships.

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

Do not create Terraform modules merely for architectural appearance.

Extract modules only when repetition or reuse creates a concrete need.

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

Docker Compose can later reproduce the local multi-service environment.

---

# GitHub Actions

GitHub Actions answers:

> How do I automatically verify/build the application whenever the repository changes?

It is preferred here over Jenkins because the project is intended to be a public GitHub portfolio repository and Jenkins has already been demonstrated elsewhere.

---

# AWS ECS + Fargate

ECS answers:

> How do I run and manage my application containers?

Fargate removes the need to provision and maintain EC2 container hosts.

This allows the project to focus first on:

- container deployment;
- configuration;
- task definitions;
- service lifecycle;
- image delivery;

without adding server administration.

---

# ECR

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

# Terraform

Terraform answers:

> How can another environment reproduce the infrastructure I created?

It should describe infrastructure that is already conceptually understood.

Terraform is therefore intentionally the final step of Phase 6.

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
