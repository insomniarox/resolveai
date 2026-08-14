# ResolveAI

ResolveAI is an AI incident investigation copilot built entirely with synthetic
operational data. The current workflow investigates synthetic connection-pool
and certificate-expiration incidents, reports when available evidence is
insufficient, and retrieves related runbook knowledge from PostgreSQL. The fake
model still diagnoses from evidence alone: retrieved similarity is neither
causal evidence nor diagnosis confidence.

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
        build_runbook_query()                         generate_hypothesis(evidence)
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

### 5. The fake proposes a hypothesis

`generate_hypothesis()` receives only the evidence list. It does not receive
`INC-001`, so it cannot select a canned answer by incident ID.

The pool rule finds a connection timeout and the latest connection-pool setting
change by comparing evidence timestamps. It produces a diagnosis only when that
latest change reduced the pool. An older reduction followed by a later
restoration therefore cannot trigger a stale diagnosis. The scan does not sort
or mutate the collected evidence list.

When the rule matches, it returns a `Hypothesis` containing a probable cause,
confidence, remediation, and the two evidence IDs it wants to cite.

The hypothesis is still unverified. A future LLM could cite an identifier that
does not exist, so model-shaped output is not used as the final response yet.

If no rule matches, the fake raises `InsufficientEvidenceError`. The orchestrator
treats this specific exception as an expected outcome and builds an inconclusive
result. It does not catch unrelated exceptions, because those would indicate an
unexpected application failure rather than uncertainty about the diagnosis.

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
| `resolve_ai/fake_model.py` | How is evidence mapped to a testable hypothesis? |
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

The original corpus was expanded without modifying its three runbooks or six
cases. Each existing topic now has a realistic, confusable neighbor:

- database connection-pool exhaustion versus blocked transactions;
- client authentication certificates versus upstream TLS server certificates;
- external notification-provider outages versus internal delivery-worker lag.

The resulting benchmark contains six runbooks and twelve cases: six direct
vocabulary queries and six paraphrased information needs. The new documents,
queries, labels, embedding model, and ranking implementations were frozen before
either evaluator was run.

### Expanded benchmark results

```text
                         Direct    Paraphrased    Overall
Lexical                    5/6         0/6          5/12
Semantic                   6/6         5/6         11/12
```

The complete rankings returned with `limit=3` were:

| Case | Expected | Lexical ranking | Semantic ranking |
|---|---|---|---|
| `pool-direct` | RUN-001 | RUN-001 | RUN-001, RUN-004, RUN-003 |
| `pool-paraphrased` | RUN-001 | no results | RUN-004, RUN-001, RUN-003 |
| `certificate-direct` | RUN-002 | RUN-002 | RUN-002, RUN-005, RUN-003 |
| `certificate-paraphrased` | RUN-002 | no results | RUN-002, RUN-005, RUN-003 |
| `provider-direct` | RUN-003 | RUN-003 | RUN-003, RUN-006, RUN-001 |
| `provider-paraphrased` | RUN-003 | no results | RUN-003, RUN-005, RUN-001 |
| `lock-direct` | RUN-004 | RUN-004 | RUN-004, RUN-001, RUN-005 |
| `lock-paraphrased` | RUN-004 | no results | RUN-004, RUN-001, RUN-003 |
| `upstream-tls-direct` | RUN-005 | no results | RUN-005, RUN-002, RUN-001 |
| `upstream-tls-paraphrased` | RUN-005 | no results | RUN-005, RUN-002, RUN-001 |
| `queue-backlog-direct` | RUN-006 | RUN-006 | RUN-006, RUN-003, RUN-004 |
| `queue-backlog-paraphrased` | RUN-006 | no results | RUN-006, RUN-003, RUN-001 |

Semantic retrieval had six unique Top-1 wins: `certificate-paraphrased`,
`provider-paraphrased`, `lock-paraphrased`, `upstream-tls-direct`,
`upstream-tls-paraphrased`, and `queue-backlog-paraphrased`. Lexical retrieval
had no unique wins. Both strategies missed `pool-paraphrased`; semantic retrieval
ranked its expected RUN-001 second behind the new RUN-004. Top-1 and the visible
case rankings are sufficient to describe this result without adding another
metric.

## Verify

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
