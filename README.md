# ResolveAI

ResolveAI is an AI incident investigation copilot built entirely with synthetic
operational data. The current workflow investigates synthetic connection-pool
and certificate-expiration incidents, reports when available evidence is
insufficient, and retrieves related runbook knowledge from PostgreSQL. The API
defaults to an evidence-only deterministic fake, while the frozen benchmark can
also run one structured OpenAI reasoner. Retrieved similarity is neither causal
evidence nor diagnosis confidence.

## Run locally

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

Discover the available incidents:

```bash
curl http://127.0.0.1:8000/incidents
```

Investigate an incident:

```bash
curl -X POST http://127.0.0.1:8000/incidents/INC-001/investigate
curl -X POST http://127.0.0.1:8000/incidents/INC-002/investigate
curl -X POST http://127.0.0.1:8000/incidents/INC-003/investigate
```

## Run the frontend locally

The frontend uses pnpm 11.21.0, pinned in `web/package.json`. It expects the
PostgreSQL prerequisites and FastAPI process above to be running at
`http://127.0.0.1:8000`. In a second terminal:

```bash
cd web
cp .env.local.example .env.local
corepack enable
pnpm install --frozen-lockfile
pnpm run dev
```

Open `http://localhost:3000`. The browser calls same-origin `/api` URLs and
Next.js proxies them to the FastAPI base URL configured by
`RESOLVEAI_API_URL`. Change that value in `web/.env.local` when the backend runs
at a different location.

## Phase 4 — Reviewer-facing investigation UI

The UI gives a reviewer a direct way to understand an investigation without
reading raw API responses. It deliberately visualizes only behavior that the
current application exposes:

```text
FastAPI JSON
        ↓
Next.js dashboard
        ↓
incident selection
        ↓
synchronous investigation
        ↓
diagnosis / inconclusive
        ↓
Evidence + citations + reference knowledge
```

The single responsive App Router page uses local React state and native `fetch`.
It shows only truthful request states—Ready, Investigating, Complete, and
Failed—because FastAPI returns one final synchronous `InvestigationResult` and
does not expose internal progress events.

The presentation keeps all collected Evidence visible, highlights the subset
cited by `Diagnosis.supporting_evidence_ids`, and displays RetrievedRunbooks in a
separate reference-knowledge section. Human approval remains informational
because ResolveAI currently recommends remediation but performs no mutating
action. The Next.js rewrite connects the browser to FastAPI through the
configurable `RESOLVEAI_API_URL`, so no FastAPI CORS change was needed.

A manual local smoke test ran PostgreSQL, FastAPI, and Next.js together
successfully. `INC-001` rendered the connection-pool diagnosis with cited
Evidence, confidence, remediation, approval information, and separate runbooks;
`INC-002` rendered the expired-client-certificate diagnosis and citation;
`INC-003` rendered a successful inconclusive result with no invented Diagnosis
while retaining Evidence and reference knowledge. The rewrite also preserved
the existing FastAPI 404 response. This smoke test is not automated browser
coverage.

Phase 4 is complete because this flow satisfies the current reviewer need.
Progress visualization, intermediate hypotheses, tool calls, and approval
controls remain postponed until corresponding application capabilities exist:

> UI capability should follow real application capability.

## How one investigation works

The application is a single Python process. FastAPI does not perform the
investigation itself; it exposes an ordinary Python workflow through HTTP.

```text
POST /incidents/INC-001/investigate
                │
                ▼
api.py: investigate_incident_endpoint()
                │ loads synthetic data
                ▼
fixtures.py: get_incident_context()
                │ returns IncidentContext
                ▼
investigation.py: investigate_incident()
                │
                ├── inspect_logs() ─────────┐
                └── inspect_deployments() ──┤ produce Evidence objects
                                            │
                   ┌────────────────────────┴───────────────────────┐
                   ▼                                                ▼
        build_runbook_query()                         selected HypothesisGenerator
                   │                                                │
                   ▼                                     supported │ no rule
        semantic_search_runbooks()                       hypothesis │
                   │                                                │
                   ▼                                                ▼
        ordered RetrievedRunbooks                 diagnosed or inconclusive
                   │                                                │
                   └────────────────────────┬───────────────────────┘
                                            ▼
                                 InvestigationResult
                │ FastAPI serializes it
                ▼
             JSON response
```

### 1. The API receives an incident ID

The route in `resolve_ai/api.py` receives `INC-001` from the URL. It knows about
HTTP concerns such as returning status `404`, but it contains no diagnosis rules.

### 2. The fixture supplies raw operational data

`get_incident_context("INC-001")` returns an `IncidentContext` containing:

- the reported incident;
- application log records;
- deployment-history records.

The fixture is an in-memory substitute for production log and deployment
systems. PostgreSQL is used only for the runbook corpus in this milestone.

### 3. Raw records become evidence

Logs and deployments have different fields. The inspection functions convert
both into the shared `Evidence` shape:

```text
Evidence
├── id            exact source record to cite
├── source        log or deployment
├── kind          operational fact represented
├── observed_at   when it happened
├── summary       human-readable explanation
└── details       structured values needed by a rule
```

For `INC-001`, this produces evidence including:

- `LOG-001`: a database connection timed out;
- `DEP-001:database_connection_pool_size`: the pool changed from 20 to 5.

This conversion is called normalization: different source formats are converted
into one common format without losing their source identity.

### 4. The workflow retrieves related runbooks

The workflow deterministically builds one query from the incident title,
description, and collected evidence summaries. It embeds that text once and
asks PostgreSQL/pgvector for the three most similar runbooks. PostgreSQL failures
remain system failures; they are not converted into an empty retrieval list or
an inconclusive investigation.

The ordered results are `RetrievedRunbook` objects. They are operational
reference material and remain separate from `Evidence`, which represents facts
observed in this incident.

### 5. The selected reasoner proposes a hypothesis

`investigate_incident()` accepts one small callable boundary: incident,
`Evidence`, and `RetrievedRunbook` values enter; a structured `Hypothesis`
returns. The API defaults to `generate_fake_hypothesis()`, whose adapter discards
the incident and runbooks before calling the original evidence-only fake. The
fake therefore still cannot select a canned answer by incident or runbook ID.

The pool rule finds a connection timeout and the latest connection-pool setting
change by comparing evidence timestamps. It produces a diagnosis only when that
latest change reduced the pool. An older reduction followed by a later
restoration therefore cannot trigger a stale diagnosis. The scan does not sort
or mutate the collected evidence list.

When a reasoner reaches a diagnosis, it returns a `Hypothesis` containing both a
normalized root-cause label and a human-readable probable cause, plus confidence,
remediation, and the evidence IDs it wants to cite.

The hypothesis is still unverified. A future LLM could cite an identifier that
does not exist, so model-shaped output is not used as the final response yet.

If no rule matches, the fake raises the shared `InsufficientEvidenceError`. The
OpenAI reasoner raises the same exception when its structured decision is
inconclusive. The orchestrator treats only this exception as an expected outcome;
database, SDK, schema, and other unexpected failures remain system failures.

### 6. The application verifies citations

`verify_hypothesis()` creates a lookup from collected evidence IDs to their full
objects. It rejects the hypothesis if any cited ID is absent. For Phase 1, it
does not attempt to prove that the evidence logically guarantees the conclusion.

After this check, the verified citation IDs are copied into
`Diagnosis.supporting_evidence_ids`. Their order remains the order chosen by the
hypothesis. The root cause, confidence, remediation, approval requirement, and
supporting IDs therefore form one complete diagnosis.

`InvestigationResult.evidence` always contains every observation collected by
the workflow, in collection order. For `INC-001`, that includes `LOG-002` even
though it is not part of the diagnosis's supporting subset. This lets a caller
distinguish what ResolveAI inspected from what it used to support its conclusion.
`InvestigationResult.retrieved_runbooks` separately contains the ranked
reference material. Its similarity scores describe query relevance only, and
runbook IDs cannot become `Diagnosis.supporting_evidence_ids`.

For an inconclusive investigation, the result instead contains:

- `status: "inconclusive"`;
- `diagnosis: null` rather than partially empty diagnosis fields;
- all evidence that was collected;
- the retrieved runbooks, in retrieval order.

### 7. FastAPI returns JSON

FastAPI validates the `InvestigationResult` with Pydantic and serializes it into
the JSON response received by the caller.

## Code map

| File | Question it answers |
|---|---|
| `resolve_ai/api.py` | How does an HTTP request enter the application? |
| `resolve_ai/fixtures.py` | Where does Phase 1 operational data come from? |
| `resolve_ai/models.py` | What shape does data have at each stage? |
| `resolve_ai/investigation.py` | In what order do investigation steps run? |
| `resolve_ai/reasoning.py` | What is the shared reasoner callable contract? |
| `resolve_ai/fake_model.py` | How is evidence mapped to a testable hypothesis? |
| `resolve_ai/openai_model.py` | How does one real model produce structured reasoning? |
| `resolve_ai/embeddings.py` | How do runbook and query texts become vectors? |
| `resolve_ai/retrieval.py` | How are runbooks ranked by PostgreSQL? |
| `tests/test_investigation.py` | Does the domain logic behave correctly by itself? |
| `tests/test_api.py` | Does the public HTTP contract behave correctly? |

## Deliberate Phase 1 limitations

- Data is held in Python fixtures rather than a database.
- The fake supports only two explicit evidence patterns.
- Evidence outside those patterns produces a structured inconclusive result.
- Confidence values are illustrative, not statistically calibrated.
- Verification checks citation existence, not whether evidence proves causality.
- Recommended actions are returned but never executed.

## Phase 2 lexical retrieval baseline

The lexical baseline remains an independent operation. `search_runbooks()`
queries PostgreSQL directly and returns ranked runbooks; the investigation
workflow does not call it.

### Start PostgreSQL locally

The Compose file runs only the PostgreSQL dependency. It does not containerize
the FastAPI application and is not Phase 6 application packaging.

```bash
docker compose up -d database
```

The PostgreSQL image runs `database/init.sql` automatically only when it creates
a fresh database volume. Restarting a container with an existing volume does not
rerun initialization scripts. This milestone deliberately uses one idempotent
SQL file rather than introducing a migration framework.

The local development connection string is:

```text
postgresql://resolveai:resolveai@localhost:5432/resolveai
```

### Search the runbooks

The database URL is passed explicitly so the database dependency is visible at
the call site:

```python
from resolve_ai.retrieval import search_runbooks

results = search_runbooks(
    database_url="postgresql://resolveai:resolveai@localhost:5432/resolveai",
    query='"connection pool" OR timeout',
    limit=3,
)
```

PostgreSQL converts each runbook title and body into a weighted `tsvector`.
`websearch_to_tsquery` converts the supplied text into a query, `@@` selects
lexical matches, and `ts_rank` orders them. A rank score is meaningful only for
comparing results from the same query; it is not a probability.

Each runbook is currently one database row and one retrieval chunk. The lexical
operation uses only its generated `tsvector`; it does not consume the separate
stored embedding, perform hybrid ranking, or connect retrieval to diagnosis.

### Run the database integration test

```bash
TEST_DATABASE_URL=postgresql://resolveai:resolveai@localhost:5432/resolveai \
  uv run pytest -m integration
```

The integration test applies the idempotent SQL, calls the real
`search_runbooks()` operation, and verifies title/body-weighted lexical ranking.
Without `TEST_DATABASE_URL`, the database test is skipped rather than silently
using an unintended database.

### Measure the lexical baseline

The strategy-neutral benchmark in `evals/runbook_retrieval_cases.json` contains
one direct-vocabulary query and one paraphrased query for each runbook. Its
human-labeled expected IDs can be reused unchanged when later retrieval
strategies are evaluated.

Run the PostgreSQL lexical evaluator against the local database:

```bash
uv run python -m evals.evaluate_lexical_retrieval \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai
```

The evaluator calls the real `search_runbooks()` operation and reports Top-1
accuracy: the proportion of cases whose expected runbook is the first returned
result. An empty result is a miss. Benchmark misses are measurements, not test
failures; regression tests separately verify that search and metric calculation
behave as designed.

On the original three-runbook, six-case corpus, the lexical implementation
measured:

```text
Overall Top-1:           3/6 (50%)
Direct vocabulary:      3/3 (100%)
Paraphrased:             0/3 (0%)
```

The direct cases show that the lexical baseline handles queries sharing the
runbooks' important vocabulary. The original paraphrased cases return no results
because they lack sufficient searchable vocabulary overlap with their relevant
runbooks. This is a concrete baseline limitation to compare with a future
semantic strategy; it is not a claim that PostgreSQL full-text search can never
retrieve differently worded queries.

## Phase 2 semantic retrieval baseline

Semantic retrieval is a second concrete operation beside lexical retrieval. It
does not replace `search_runbooks()`. The investigation workflow now uses this
operation to attach related knowledge to its result, while diagnosis remains
evidence-only.

Each complete runbook remains one row and one retrieval chunk. FastEmbed's fixed
`BAAI/bge-small-en-v1.5` model converts this stable representation into a
384-dimensional document embedding:

```text
Title: <runbook title>

Content: <runbook content>
```

The title and content are embedded because they contain the runbook's semantic
meaning. The runbook ID and service remain structured fields and are not added
to the embedding text.

### How one semantic search works

The boundary between embedding generation and database retrieval is explicit:

```text
query text
    ↓
embeddings.py: generate_query_embedding()
    ↓ returns ordinary list[float]
retrieval.py: _format_vector_for_postgres()
    ↓ produces one bound SQL parameter
PostgreSQL: parameter::vector(384)
    ↓ orders runbooks by embedding <=> query vector
ranked RetrievedRunbook objects
```

`<=>` is pgvector cosine distance, so smaller distances rank first. The returned
`similarity_score` is `1 - cosine distance`, making larger values more similar.
It is a model-specific ranking score, not a probability or diagnosis confidence.

The database performs exact vector comparisons over the six runbooks. There
is deliberately no approximate vector index, score threshold, hybrid ranking,
reranker, metadata filter, or retrieval framework.

### Retrieval-enriched investigation

`investigate_incident()` collects evidence, constructs the query, and calls
`semantic_search_runbooks()` with a fixed limit of three. The result preserves
the database ranking order. Query embedding generation and pgvector SQL remain
visible as separate steps in `resolve_ai/retrieval.py`; no generic retriever or
dependency-injection framework sits between them.

The deterministic fake receives only `list[Evidence]`, not retrieved runbooks.
Changing retrieved candidates therefore cannot change its diagnosis. Retrieved
knowledge can still accompany an inconclusive result, which distinguishes “no
supported diagnosis from the observed evidence” from “retrieval returned
nothing.” Database configuration and retrieval errors propagate as application
failures instead of being mislabeled as inconclusive outcomes.

### Populate document embeddings

Document vectors are stored in the existing nullable `runbooks.embedding`
column. Apply the idempotent SQL explicitly when using a database volume created
before pgvector was added:

```bash
docker compose up -d database
docker compose exec -T database \
  psql -U resolveai -d resolveai -v ON_ERROR_STOP=1 \
  < database/init.sql
```

Then generate only the missing document embeddings:

```bash
uv run python -m resolve_ai.populate_runbook_embeddings \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai
```

The first invocation downloads the fixed public model artifact. Inference is
local after that download. Subsequent population runs report zero unless a new
runbook was added or an existing title/content change invalidated its vector.
Searches reuse these stored document embeddings and generate only the current
query embedding.

### Measure the semantic baseline

The semantic evaluator reads the same unchanged
`evals/runbook_retrieval_cases.json` used by the lexical evaluator:

```bash
uv run python -m evals.evaluate_semantic_retrieval \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai
```

With the fixed model and original three-runbook, six-case corpus, the semantic
baseline measured:

```text
Overall Top-1:           6/6 (100%)
Direct vocabulary:      3/3 (100%)
Paraphrased:             3/3 (100%)
```

The semantic strategy retained every direct-vocabulary result and recovered all
three paraphrased queries missed by lexical retrieval. This six-case synthetic
benchmark is useful for demonstrating the mechanism and the measured contrast,
but it is too small to establish general retrieval quality.

## Expanded retrieval benchmark

The Phase 2 corpus introduced three confusable topic pairs: connection-pool
exhaustion versus database locking, client-certificate expiration versus
upstream server identity, and provider outage versus worker backlog. Phase 3
then added three organization-specific knowledge documents and six frozen
queries without changing the embedding model or either ranking implementation.

The current nine-runbook, eighteen-query benchmark measures:

```text
                         Direct    Paraphrased    Overall
Lexical                    5/9         0/9          5/18
Semantic                   9/9         7/9          16/18
```

On the six new knowledge-document queries, semantic retrieval achieved 5/6
Top-1 and 6/6 Top-3 delivery. Lexical retrieval returned no result for those six
queries. Semantic retrieval therefore remains the selected investigation
strategy; the case-level evidence still does not justify hybrid retrieval.

## Phase 3 investigation evaluation

Phase 3 contains two independently frozen slices:

- `evals/investigation_cases.json`: the seven-case core benchmark;
- `evals/investigation_retrieval_cases.json`: three retrieval-dependent cases.

Use `--benchmark core`, `--benchmark retrieval-dependent`, or
`--benchmark combined` to select the slice. Ground truth remains independent of
the fake and Luna and includes normalized root causes, required and acceptable
Evidence IDs, relevant runbooks, and remediation labels.

### Evaluator semantics

The initial deterministic metrics are status accuracy, normalized root-cause
accuracy, citation precision, and citation recall. Case outcomes preserve these
distinctions:

- a wrong status or root cause is `incorrect_answer`;
- real Evidence outside the acceptable set reduces citation precision and can
  produce `correct_with_extraneous_evidence`;
- an unavailable Evidence citation is an unsupported grounding failure;
- retrieval, API, schema, and other execution failures are `system_failure`.

Citation precision and recall apply only to correctly diagnosed root causes.
Precision uses `acceptable_supporting_evidence_ids`; recall uses
`required_supporting_evidence_ids`. Unsupported citation IDs remain visible even
when the root cause is wrong, but the wrong diagnosis receives no citation score.

### Baseline progression

The evidence-only deterministic fake establishes the initial reasoning floor:

```text
Status accuracy:             3/7 (43%)
Root-cause accuracy:         2/6 (33%)
Evidence citation precision: 3/3 (100%)
Evidence citation recall:    3/3 (100%)
```

The corrected citation denominator contains only the fake's two correct
diagnoses. Its limited root-cause accuracy is measured behavior, not a failing
regression test.

GPT-5.6 Luna through OpenRouter then measured 7/7 status accuracy and 6/6
root-cause accuracy on the core benchmark. Removing runbooks produced identical
case outputs, showing that the core primarily measures reasoning over operational
Evidence rather than knowledge augmentation.

The resulting limitation justified a separate retrieval-dependent slice. Three
paired repetitions per condition measured:

| Metric | Luna + runbooks | Luna without runbooks |
|---|---:|---:|
| Status accuracy | 7/9 (78%) | 7/9 (78%) |
| Root-cause accuracy | 7/9 (78%) | 4/9 (44%) |
| Citation precision over correct diagnoses | 19/19 (100%) | 11/11 (100%) |
| Citation recall over correct diagnoses | 14/14 (100%) | 8/8 (100%) |
| Correct answers | 7/9 | 4/9 |
| Incorrect answers/outcomes | 2/9 | 5/9 |
| Unsupported citations | 0 | 0 |

The clearest effect was `INC-010`: with runbooks Luna selected provider outage
twice and became inconclusive once; without runbooks it selected the competing
worker-backlog cause in all three repetitions. The organization-specific
lifecycle knowledge removed that repeated wrong diagnosis. `INC-009` improved
from 1/3 to 2/3 correct, while `INC-008` remained 3/3 in both conditions.

The benchmark-scoped conclusion is:

> Retrieved organization-specific knowledge demonstrated measurable
> investigation value for GPT-5.6 Luna on the frozen retrieval-dependent
> synthetic benchmark.

This does not establish that retrieval always helps, that Top-3 is globally
optimal, or that the result generalizes beyond these synthetic cases.

### Run an investigation evaluation

The real reasoner uses GPT-5.6 Luna through the Responses API with Pydantic
Structured Outputs. It preserves a human-readable probable cause beside the
normalized label and keeps retrieved knowledge separate from observed Evidence.

For direct OpenAI access, place `OPENAI_API_KEY` in the ignored `.env` and use
`--reasoner openai`. For OpenRouter, set `OPENROUTER_API_KEY` and use:

```bash
uv run python -m evals.evaluate_investigations \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai \
  --reasoner openrouter \
  --benchmark retrieval-dependent \
  --runbooks enabled
```

Changing only `--runbooks disabled` supplies an empty runbook sequence to the
same reasoner boundary. There is no fallback, routing, prompt-management layer,
LangChain, or LangGraph.

### Known evaluation limitations

- all ten incidents are synthetic;
- only three cases test retrieval-dependent knowledge;
- real-model behavior is nondeterministic;
- `INC-009` and `INC-010` were not perfectly stable with retrieval;
- `INC-008` did not demonstrate retrieval value;
- retrieval utility was measured only with GPT-5.6 Luna;
- no prompt optimization, model comparison, hybrid retrieval, reranking, or
  query rewriting was performed.

Phase 3 and Phase 4 are complete. Phase 5 — Observability is next and has not
started.

## Verify

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Verify the frontend with its pinned pnpm version:

```bash
cd web
corepack enable
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run lint
pnpm run build
```
