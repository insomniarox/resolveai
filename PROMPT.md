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

Phase 6 is further divided into:

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

## 6.3 Cloud Deployment — AWS ECS + Fargate

### Learning question

> Where does the container actually run?

Do not deploy to AWS until:

- the application works locally;
- the Docker image works locally;
- CI can verify/build the application.

Use:

```text
ECR
ECS task definition
ECS service
Fargate
environment configuration
secrets
```

Introduce these concepts one at a time.

### ECR

Explain:

> Where does the built Docker image live?

Show the flow:

```text
source code
    ↓
Docker image
    ↓
ECR
```

### ECS task definition

Explain:

> What does AWS need to know in order to run this container?

Keep the explanation tied to:

- container image;
- CPU;
- memory;
- port;
- environment variables;
- secrets.

### ECS service

Explain:

> How does AWS keep the desired application task running?

Introduce:

- desired task count;
- service deployment;
- task replacement;
- basic health behavior.

### Fargate

Explain:

> Why are we using Fargate rather than managing EC2 container hosts?

The reason should be pedagogical and architectural:

> Fargate lets us learn container deployment before adding server provisioning and operating-system management.

### Environment and secrets

Explain the difference between:

- source code;
- configuration;
- environment variables;
- secrets.

Never commit credentials.

Do not add unrelated AWS services merely because they are commonly found in architecture diagrams.

If an additional AWS resource is needed, first explain:

1. the concrete problem;
2. the simplest alternative;
3. why the AWS resource is justified.

---

## 6.4 Terraform — Infrastructure as Code

### Learning question

> How do I describe and reproduce the infrastructure?

Terraform must come **after** the AWS architecture has been understood.

Do not use Terraform as the first way of learning what ECS, ECR, or Fargate do.

The desired progression is:

```text
understand infrastructure
        ↓
create a working deployment
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

The final Terraform should reproduce the infrastructure required to deploy ResolveAI.

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


