# ResolveAI

ResolveAI is a portfolio-scale incident investigation copilot built with
synthetic data. It has three reviewer paths:

- a guided path with three prepared incidents and a deterministic reasoner;
- a runtime path that accepts a bounded JSON bundle and uses one server-selected
  GPT-5.6 Luna provider;
- an experimental comparison path that assesses user-supplied hypotheses with
  OpenRouter and Jev concurrently against shared evidence and references.

The guided and ordinary runtime paths collect or accept observed Evidence,
retrieve related runbooks from
PostgreSQL with pgvector, ask a reasoner for a structured hypothesis, verify its
Evidence citations, and return a diagnosed or inconclusive result.

The project is a showcase exercise, not a hosted platform. It has no accounts,
workspaces, autonomous remediation, durable background jobs, or general-purpose tool
execution.

For a visual architecture walkthrough, open
[docs/case-study.html](docs/case-study.html). For a file-by-file reading order,
use [docs/code-study.md](docs/code-study.md).

## What the application proves

The current implementation demonstrates these boundaries:

- prepared and previously unseen incident input reach the same investigation
  function after normalization;
- observed Evidence stays separate from retrieved reference knowledge;
- only Evidence IDs can support a diagnosis;
- runtime documents remain in a request-specific PostgreSQL scope and are
  deleted after use;
- a model can abstain through a normal inconclusive result;
- provider, validation, citation, timeout, and storage failures have stable
  public categories;
- callers can explicitly save an immutable one-hour run with a bearer
  capability, compare two runs, and delete them;
- frozen evaluators measure retrieval, reasoning, citation, cleanup, and corpus
  isolation without changing product behavior.

The application does not establish production reliability or general incident
reasoning. Its benchmark is small and synthetic. Confidence is model output, not
a calibrated probability.

## Architecture

The backend is an ordinary synchronous Python workflow. FastAPI handles HTTP but
does not contain investigation logic.

```text
prepared fixture or runtime JSON
             |
             v
       Incident + Evidence
             |
             v
build deterministic retrieval query
             |
             v
semantic Top-3 frozen runbooks
and optional scoped runtime documents
             |
             v
deterministic fake or configured live reasoner
             |
      +------+------+
      |             |
      v             v
  Hypothesis    insufficient Evidence
      |             |
      v             v
verify Evidence  inconclusive result
citations
      |
      v
diagnosed result
```

The runtime path adds two operations around that shared workflow:

```text
validated runtime bundle
    |
    +-- optional documents -> embed -> scoped PostgreSQL rows
    |
    +-- execute shared investigation
    |
    +-- always attempt scoped-document cleanup
    |
    +-- return transient result
        or save one immutable provenance snapshot
```

### Data boundaries

`Evidence` represents incident facts. Logs, deployment changes, and normalized
runtime observations use this type. A diagnosis may cite only Evidence IDs.

`RetrievedRunbook` and `RetrievedKnowledgeDocument` represent reference text.
Their similarity scores describe retrieval relevance. The scores are not causal
support or diagnosis confidence.

`Hypothesis` is unverified reasoner output. `verify_hypothesis()` rejects any
citation that does not name collected Evidence. Only then does the application
construct a `Diagnosis`.

### Storage and retention

| Data | Location | Lifetime |
|---|---|---|
| Prepared incidents, logs, and deployments | Python fixtures | Process lifetime |
| Frozen runbooks and embeddings | PostgreSQL | Durable benchmark corpus |
| Runtime knowledge documents | PostgreSQL scope | Deleted after the request, with a 15-minute expiry fallback |
| Transient runtime input and result | Not stored | Request lifetime |
| Explicitly saved run | PostgreSQL JSONB snapshot | One hour |
| Saved-run capability | Plaintext held by the caller, SHA-256 digest in PostgreSQL | One hour or until deletion |

There is no saved-run list or update route. Missing, expired, deleted, and
unauthorized saved runs all return the same 404 response.

## HTTP API

| Method and path | Purpose |
|---|---|
| `GET /incidents` | List the three prepared synthetic incidents. |
| `POST /incidents/{incident_id}/investigate` | Run the guided deterministic investigation. |
| `GET /runtime/reasoner` | Return safe provider and model metadata. |
| `GET /runtime/comparison` | Return comparison models, protocol, and configuration availability. |
| `POST /runtime/compare` | Stream a transient paired hypothesis comparison as NDJSON. |
| `POST /runtime/investigate` | Investigate one validated runtime bundle without saving it. |
| `POST /runtime/runs` | Investigate and save one one-hour immutable snapshot. |
| `GET /runtime/runs/{run_id}` | Read a saved run with its bearer capability. |
| `DELETE /runtime/runs/{run_id}` | Delete a saved run with its bearer capability. |

The runtime bundle has schema version 1. It accepts one incident, 1 to 50
Evidence items, and up to five optional text or Markdown documents. Each
document is limited to 8,000 characters and the combined document text is
limited to 20,000 characters. IDs must be unique, timestamps need a UTC offset,
and unknown fields are rejected.

Ordinary runtime inference uses exactly one server-selected provider:

| Configuration | Model | Secret |
|---|---|---|
| `RESOLVEAI_RUNTIME_PROVIDER=openrouter` | `openai/gpt-5.6-luna` | `OPENROUTER_API_KEY` |
| `RESOLVEAI_RUNTIME_PROVIDER=openai` | `gpt-5.6-luna` | `OPENAI_API_KEY` |

The provider call uses medium reasoning, a 4,000 output-token limit, a 30-second
timeout, and no SDK retries. There is no provider picker, caller-supplied key, or
fallback to the deterministic fake.

## Run locally

The backend requires Python 3.13, uv, PostgreSQL 17, and pgvector.

```bash
uv sync
docker compose up -d database
docker compose exec -T database \
  psql -U resolveai -d resolveai -v ON_ERROR_STOP=1 \
  < database/init.sql
uv run python -m resolve_ai.populate_runbook_embeddings \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai
DATABASE_URL=postgresql://resolveai:resolveai@localhost:5432/resolveai \
  uv run uvicorn resolve_ai.api:app --reload
```

Check the guided path:

```bash
curl http://127.0.0.1:8000/incidents
curl -X POST http://127.0.0.1:8000/incidents/INC-001/investigate
curl -X POST http://127.0.0.1:8000/incidents/INC-003/investigate
```

`INC-001` is diagnosed. `INC-003` is deliberately inconclusive.

To use the runtime path, copy `.env.example` to `.env`, select one provider, and
add its capped API key. The Runtime input tab contains a structured form and an
editable JSON view of the same valid bundle. The form also accepts short `.txt`
and `.md` files as request-scoped reference documents.

### Frontend development

The frontend uses Node.js 24, Next.js 16, React 19, and pnpm 11.21.0.

```bash
cd web
cp .env.local.example .env.local
corepack enable
pnpm install --frozen-lockfile
pnpm run dev
```

Open `http://127.0.0.1:3000`. Next.js rewrites same-origin `/api` requests to the
FastAPI address in `RESOLVEAI_API_URL`.

Frontend checks stay small and local:

```bash
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

### Complete Docker topology

```bash
docker compose build api web
docker compose up -d database api web
docker compose exec api python -m resolve_ai.populate_runbook_embeddings \
  --database-url postgresql://resolveai:resolveai@database:5432/resolveai
```

Open `http://127.0.0.1:3000`. The browser talks only to Next.js. The frontend
container reaches FastAPI through the Compose name `api`, and FastAPI reaches
PostgreSQL through `database`.

The frontend rewrite is compiled during `next build`. Changing
`RESOLVEAI_API_URL` for a production image therefore requires rebuilding the
web image.

## Code map

| Area | Main files |
|---|---|
| Domain data | `resolve_ai/models.py` |
| Prepared inputs | `resolve_ai/fixtures.py` |
| Deterministic reasoner | `resolve_ai/fake_model.py` |
| Shared orchestration and citation verification | `resolve_ai/investigation.py` |
| Embeddings and PostgreSQL retrieval | `resolve_ai/embeddings.py`, `resolve_ai/retrieval.py` |
| Runtime input validation | `resolve_ai/runtime_input.py` |
| Live model adapters | `resolve_ai/openai_model.py`, `resolve_ai/openrouter_model.py`, `resolve_ai/runtime_reasoner.py` |
| Runtime execution and cleanup | `resolve_ai/runtime_investigation.py` |
| Saved-run snapshots | `resolve_ai/investigation_runs.py` |
| HTTP translation | `resolve_ai/api.py` |
| Browser API contract and runtime bundle helpers | `web/lib/types.ts`, `web/lib/api.ts`, `web/lib/runtime-bundle.ts` |
| Guided and runtime UI | `web/components/` |
| Database schema and corpus | `database/init.sql` |
| Frozen benchmarks | `evals/` |
| Behavior specifications | `tests/` |

The code-study guide explains why this reading order is better than starting at
`api.py` and following imports in every direction.

## Evaluation

The repository keeps product behavior and frozen evaluation data separate.
Runtime input never enters the fixture set or the nine-runbook corpus.

The main measured results are:

| Evaluation | Result |
|---|---|
| Expanded lexical retrieval | 5/18 Top-1 |
| Expanded semantic retrieval | 16/18 Top-1 |
| Retrieval-dependent reasoning with runbooks | 7/9 correct root causes |
| Retrieval-dependent reasoning without runbooks | 4/9 correct root causes |
| Phase 7.4 runtime required-document Top-3 | 4/4 |
| Phase 7.4 live status and abstention | 15/15 status, 3/3 abstention |
| Phase 7.4 exact runtime labels | 0/12 |
| Phase 7.6 runtime required-document Top-3 | 6/6 |
| Phase 7.6 live status and abstention | 11/12 status, 3/3 abstention |
| Phase 7.6 exact runtime labels | 0/9 |
| Phase 7.6 human causal review | 8/8 all facets correct, 0 forbidden claims |

The Phase 7.6 report is
[evals/runtime_contract_report.md](evals/runtime_contract_report.md). The project
owner completed a blind review of the eight diagnosed outputs. All eight
contained the expected affected component, failure mode, and operational effect,
and none made a forbidden claim. The archived packet omitted citation IDs, so
causal-match citation precision and recall cannot be reconstructed.

The result is narrow but useful. Required documents stayed inside the reasoner
Top-3, citation and cleanup boundaries held, and exact generated labels were not
stable semantic identifiers. This does not justify new retrieval machinery or a
label-normalization service.

Run the Phase 7.6 deterministic evaluator with:

```bash
uv run python -m evals.evaluate_runtime_contract \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai
```

Live provider calls are opt-in and spend-bearing:

```bash
uv run python -m evals.evaluate_runtime_contract \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai \
  --live-provider openrouter \
  --repeats 3 \
  --review-packet /tmp/resolveai-phase-7-6-review.md
```

## Observability and deployment

Console OpenTelemetry export is disabled by default. Enable it for local study:

```bash
RESOLVEAI_TRACE_CONSOLE=1 \
DATABASE_URL=postgresql://resolveai:resolveai@localhost:5432/resolveai \
  uv run uvicorn resolve_ai.api:app --reload
```

One investigation emits a parent `investigation` span with retrieval, reasoning,
and citation-verification children. Runtime knowledge retrieval adds its own
embedding and PostgreSQL spans.

The showcase deployment uses Northflank. Next.js is public, while FastAPI and
PostgreSQL remain on the private project network. The database uses TLS. When
forwarding it locally, use the random port printed by Northflank and keep
`sslmode=require`; local port 5432 may reach the Docker database instead.

## Deliberate limits

These omissions keep the code aligned with the project goal:

- no accounts, tenancy, workspaces, or searchable history;
- no mutable saved runs or normalized incident database;
- no queues, schedulers, or background embedding jobs;
- no agent framework or autonomous tool loop;
- no arbitrary URL fetching or private repository access;
- no reranker, hybrid production retrieval, chunking, or separate vector store;
- no model routing or silent fallback;
- no automated semantic judge or label alias table;
- no remediation execution;
- no AWS or Terraform deployment added only for portfolio breadth.

Phase 8 has not started. A bounded read-only GitHub documentation import remains
a possible next product exercise, but it should wait until the current code has
been studied and explained.

## Verify

Backend checks:

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Real PostgreSQL checks:

```bash
docker compose up -d database
TEST_DATABASE_URL=postgresql://resolveai:resolveai@localhost:5432/resolveai \
  uv run pytest -m integration -q
```

Frontend checks:

```bash
cd web
corepack enable
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run lint
pnpm run build
```

Container configuration check:

```bash
docker compose config --quiet
```

## Jev decision experiment

A separate, opt-in evaluator compares Jev and OpenRouter on the same bounded
cause-selection and evidence-support questions. It uses six synthetic incident
families with structured, prose, paraphrased, and missing-evidence variants.
It does not change the app runtime, retrieval, or saved runs.

The existing TypeSafe SDK dependency uses `TYPESAFE_API_KEY`. Live evaluation
also requires `OPENROUTER_API_KEY`. Keys stay in `.env` or the process environment.

```bash
# Prepare and validate all requests without provider calls.
uv run python -m evals.evaluate_jev_decisions --output /tmp/jev-dry-run.jsonl
# Exactly 48 calls, two providers per input, no retries.
uv run python -m evals.evaluate_jev_decisions --live --max-calls 48 \
  --output /tmp/jev-results.jsonl
```

Output paths must be new. The JSONL artifact retains shared inputs, expected
answers separately from requests, model outputs, usage, timings, and failures.
See [the decision report](evals/jev_decision_report.md) for results and limits.

## Compare models

The Compare models tab accepts the existing runtime incident bundle plus one to
five distinct candidate hypotheses, each 3–500 characters. It requires both
`OPENROUTER_API_KEY` and `TYPESAFE_API_KEY` on the server. The current models are
`openai/gpt-5.6-luna` and `jev-1.13.0`. Compose forwards both keys to FastAPI.

The scenario picker includes ten detailed synthetic packages covering database
locks, certificate trust, message redelivery, search aliases, partner quotas, DNS
egress, database connection budgets, clock skew, request deadlines, and incomplete
telemetry. Each includes seven observations, two reference documents, and four
candidate hypotheses. Loading replaces the complete editor input without making
model calls; the original invoice example is also available. These are interactive
examples, not additional model benchmarks. The complete current request can be
inspected and downloaded as JSON, with a separate downloadable JSON Schema at
`/comparison-input.schema.json`. Server validation also enforces cross-field rules
described in that schema. Source packages live in
`web/lib/data/comparison-packages.json`.

```text
validate bundle and hypotheses
  -> ingest scoped documents and retrieve once
  -> copy identical context into OpenRouter and Jev branches
       -> select a hypothesis or abstain
       -> assess Evidence for the selected hypothesis
  -> stream each result independently
  -> clean up the shared document scope
```

Each route makes at most two calls, with 30-second SDK timeouts and no retries.
A provider failure preserves the other result. A process-local admission gate
allows one ordinary runtime investigation or one paired comparison at a time.
The request-owned worker finishes its bounded calls and cleanup if the browser
disconnects; disconnect does not cancel an in-flight SDK request.

Comparison requests use `{"bundle": <runtime bundle>, "candidates": ["..."]}`.
Events have `type` prepared, branch, error, or finished and their corresponding
payload. The browser validates event shapes, order, candidate bounds, and Evidence
IDs. A conservative 30,000-byte budget on serialized state plus questions rejects
large comparisons before provider calls; shorten evidence or documents if needed.
This extra limit does not change the ordinary runtime bundle limits.

Results show independent outcomes, a shared timing chart, reported tokens and
cost where available, evidence alignment, and a downloadable JSON report. Runtime
accuracy is explicitly not assessed. Jev Choice confidence describes concentration
among choices, not diagnosis accuracy. Reference material never becomes an
Evidence citation. Any contradictory observation or absence of supporting
observations leaves the assessment inconclusive.

Reference details show retrieval rank and cosine similarity separately for stored
runbooks and attached documents. The incident and observation summaries form the
search query; retrieval selects up to three references from each group. Both
models receive all observations and the same retrieved references with their
scores. Similarity does not filter observations or assign their evidence labels.
The reference content can inform interpretation, but the application has no fixed
score-to-observation weighting and does not measure individual reference influence.

The app copies the selected candidate text instead of generating a diagnosis or
remediation. Candidate coverage is the user's responsibility in this first
comparison feature. The open-ended runtime investigation remains available.
Comparison results are transient; existing saved-run behavior is unchanged.

The harder evaluation and production-regression results are in
[evals/jev_pressure_report.md](evals/jev_pressure_report.md). The implementation
checklist and deferred work are in [JEV_IMPLEMENTATION_PLAN.md](JEV_IMPLEMENTATION_PLAN.md).
