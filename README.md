# ResolveAI

ResolveAI is an AI incident investigation copilot whose current public runtime
uses deliberately constructed synthetic operational data. The reviewer-facing
API investigates three prepared incidents with a deterministic fake and accepts
transient runtime bundles through a server-selected GPT-5.6 Luna provider. The
runtime supports OpenRouter or direct OpenAI configuration without exposing a
provider picker or user keys. Both paths retrieve related runbook knowledge from
PostgreSQL; retrieved similarity is neither causal evidence nor diagnosis
confidence. The deployed runtime also accepts optional bounded text or Markdown
knowledge documents for one request-scoped retrieval operation.

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

Investigate one transient runtime bundle:

```bash
curl -X POST http://127.0.0.1:8000/runtime/investigate \
  -H 'Content-Type: application/json' \
  --data '{
    "schema_version": 1,
    "incident": {
      "id": "USER-INC-901",
      "title": "Checkout requests timing out",
      "description": "A previously unseen checkout service is degraded.",
      "service": "checkout-runtime-service",
      "started_at": "2026-08-17T09:00:00Z"
    },
    "evidence": [
      {
        "id": "USER-DEP-901:database_connection_pool_size",
        "source": "deployment",
        "kind": "configuration_change",
        "observed_at": "2026-08-17T08:55:00Z",
        "summary": "A deployment reduced the database connection pool.",
        "details": {
          "setting": "database_connection_pool_size",
          "previous_value": 30,
          "new_value": 6
        }
      },
      {
        "id": "USER-LOG-901",
        "source": "log",
        "kind": "database_connection_timeout",
        "observed_at": "2026-08-17T09:00:10Z",
        "summary": "Checkout timed out while acquiring a database connection.",
        "details": {}
      }
    ],
    "knowledge_documents": [
      {
        "id": "DOC-901",
        "title": "Checkout database session policy",
        "content_type": "text/markdown",
        "content": "Checkout requires at least 20 reusable database sessions during normal traffic. A smaller pool can cause callers to wait before SQL dispatch."
      }
    ]
  }'
```

The runtime bundle is validated and investigated through the configured external
inference provider. Incident input and results are not stored. Optional knowledge
documents are embedded locally, stored atomically under a server-generated scope,
retrieved only for that request, and deleted when it finishes. An interrupted
scope becomes ineligible after 15 minutes and is purged by a later ingestion. No
runtime input enters the fixture set or frozen runbook corpus. Copy `.env.example`
to `.env`, keep
`RESOLVEAI_RUNTIME_PROVIDER=openrouter`, and set a capped `OPENROUTER_API_KEY`.
To use direct OpenAI instead, select `openai` and set `OPENAI_API_KEY`. There is
no automatic provider or fake fallback.

### Enable local console traces

Tracing is disabled by default. To export one investigation trace to the
FastAPI process's console, start the backend with the explicit opt-in flag:

```bash
RESOLVEAI_TRACE_CONSOLE=1 \
DATABASE_URL=postgresql://resolveai:resolveai@localhost:5432/resolveai \
  uv run uvicorn resolve_ai.api:app --reload
```

Each completed investigation prints an `investigation` span with
`retrieve_runbooks` and `generate_hypothesis` children. `retrieve_runbooks`
contains `generate_query_embedding` and `query_runbooks`; diagnosed results also
include `verify_citations`. A runtime request with documents also includes
`retrieve_runtime_knowledge`, with query-embedding and scoped PostgreSQL children.
The output contains trace and parent IDs, start/end times, operational attributes,
and standard exception details for genuine failures. Export is batched and queued
spans flush during normal process shutdown.

## Run the application with Docker

Phase 6.1 packages FastAPI and Next.js as separate runtimes beside PostgreSQL.
Build both application images and start the complete local topology:

```bash
docker compose build api web
docker compose up -d database api web
```

Open `http://127.0.0.1:3000`. The browser reaches the published frontend port;
Next.js handles same-origin `/api` requests and forwards them to FastAPI over the
Compose network.

On a fresh PostgreSQL volume, `database/init.sql` creates the schema and corpus
automatically. Embedding generation remains an explicit setup operation rather
than an API startup side effect or a separate Compose service:

```bash
docker compose exec api python -m resolve_ai.populate_runbook_embeddings \
  --database-url postgresql://resolveai:resolveai@database:5432/resolveai
```

The API uses the repository root as its build context. The root `.dockerignore`
keeps local virtual environments, caches, secrets, and generated frontend files
out of that context. The root `Dockerfile` installs locked Python production
dependencies, copies `resolve_ai/`, and starts Uvicorn on container port 8000.

The frontend uses `web/` as a separate build context because all of its build
inputs live there. Docker therefore applies `web/.dockerignore`, not the root
ignore file. The frontend Dockerfile activates the pnpm version pinned in
`package.json`, installs the lockfile exactly, runs `next build`, and starts the
production server with `next start` on container port 3000.

The API receives its database URL through the Compose `environment` setting. A
host process uses `localhost:5432` to reach PostgreSQL's published port, while
the API container uses `database:5432`: Compose makes the service name
`database` resolvable on its private default network.

The frontend rewrite similarly uses `http://api:8000`, where `api` is the
FastAPI service's Compose DNS name. `RESOLVEAI_API_URL` is evaluated by
`next.config.ts` during `next build`, and the resolved destination is written to
the production route manifest. Compose therefore supplies the internal address
as a build argument. The same value is supplied when the container starts
because Next.js loads its config then too, but changing only the startup value
does not replace the already-built rewrite; a different backend destination
requires rebuilding the frontend image. Requests use the built route and do not
read this environment variable individually.

`depends_on` starts the database container before the API container, but it does
not wait for PostgreSQL readiness. No wait script is required because importing
the FastAPI application and starting Uvicorn do not open a database connection.
The investigation endpoint reads `DATABASE_URL` and connects only when an
investigation request reaches retrieval. The production Next.js process also
starts without contacting FastAPI, so the `web` dependency expresses startup
ordering without adding a readiness script.

## Run the frontend locally

The frontend uses pnpm 11.21.0, pinned in `web/package.json`. It expects the
PostgreSQL prerequisites and either the host-run or containerized FastAPI
process above to be reachable at
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

## How one investigation works

The backend investigation runs in a single Python process. FastAPI does not
perform the investigation itself; it exposes an ordinary Python workflow through
HTTP. The route and every current investigation operation are synchronous. There
are no background jobs, workflow events, or concurrent investigation stages.

### Current synchronous execution path

| Boundary | Current function | Behavior and failure boundary |
|---|---|---|
| HTTP request | prepared and runtime endpoints in `resolve_ai/api.py` | Loads a fixture by ID or validates one versioned runtime bundle, requires `DATABASE_URL`, and propagates unexpected workflow failures. |
| Input adaptation | `get_incident_context()` or `RuntimeIncidentBundle.to_domain()` | Copies a frozen fixture context or converts the bounded runtime DTO into one `Incident` and ordered `Evidence[]`. Runtime input is not stored. |
| Evidence collection | `inspect_logs()` and `inspect_deployments()` in `resolve_ai/investigation.py` | Select and normalize fixture records. Runtime bundles already supply normalized Evidence and do not mutate the fixture collector boundary. |
| Shared orchestration | `investigate_evidence()` in `resolve_ai/investigation.py` | Copies the domain input and runs the same retrieval, reasoning, citation-verification, and result path for both adapters. |
| Retrieval-query construction | `build_runbook_query()` in `resolve_ai/investigation.py` | Deterministically combines the incident and Evidence summaries. |
| Semantic retrieval | `semantic_search_runbooks()` in `resolve_ai/retrieval.py` | Generates one query embedding, performs a synchronous PostgreSQL/pgvector Top-3 search, and returns ordered `RetrievedRunbook` values. Embedding, database, SQL, and result-validation errors propagate. |
| Hypothesis generation | Selected `HypothesisGenerator` | Runs the local deterministic fake by default or a synchronous remote model call in an evaluator/manual path. Only `InsufficientEvidenceError` represents a normal inconclusive outcome. |
| Inconclusive handling | `_build_inconclusive_result()` in `resolve_ai/investigation.py` | Returns the collected Evidence and retrieved reference knowledge with `diagnosis: null`. |
| Citation verification | `verify_hypothesis()` in `resolve_ai/investigation.py` | Rejects cited IDs that are not present in collected Evidence, then constructs the diagnosed result. |
| HTTP response | FastAPI with `InvestigationResult` | Validates and serializes the final diagnosed or inconclusive result as JSON. |

The external operations whose duration or failure can vary materially are
semantic retrieval and, when selected outside the default API path, remote
hypothesis generation. Evidence collection, query construction, citation
verification, and result construction are currently small in-process
operations. Citation verification remains a meaningful correctness boundary
even though its duration is negligible.

### Effective flow

```text
POST /incidents/{incident_id}/investigate
→ load IncidentContext from synthetic fixtures
→ inspect logs and deployments into ordered Evidence
→ investigate_evidence()
   → read normalized Incident and Evidence
   → build deterministic retrieval query
   → generate query embedding
   → query PostgreSQL/pgvector for semantic Top-3
   → collect ordered RetrievedRunbooks
   → call selected HypothesisGenerator
      ├── InsufficientEvidenceError
      │   → build inconclusive InvestigationResult
      └── Hypothesis
          → verify cited Evidence IDs
          → build diagnosed InvestigationResult
→ FastAPI validates and serializes the result
→ JSON response
```

The runtime adapter joins the same flow after normalization:

```text
POST /runtime/investigate
→ validate schema version, sizes, IDs, timestamps, and supported field types
→ adapt RuntimeIncidentBundle into Incident + Evidence[] + KnowledgeDocument[]
→ if documents exist:
   → generate one whole-document embedding per document
   → atomically store them under a server-generated short-lived scope
→ investigate_evidence()
   → retrieve frozen Runbook Top-3
   → retrieve current-scope KnowledgeDocument Top-3
   → keep both reference lists separate from Evidence
→ return diagnosed or inconclusive InvestigationResult
→ delete the runtime knowledge scope
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
systems. PostgreSQL persists the frozen runbook corpus and only the short-lived,
request-scoped knowledge documents described by the runtime path; incidents and
Evidence are not stored.

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
| `resolve_ai/openrouter_model.py` | How is the same model reached through OpenRouter? |
| `resolve_ai/embeddings.py` | How do runbook and query texts become vectors? |
| `resolve_ai/retrieval.py` | How are runbooks ranked by PostgreSQL? |
| `tests/test_investigation.py` | Does the domain logic behave correctly by itself? |
| `tests/test_api.py` | Does the public HTTP contract behave correctly? |

## Deliberate Phase 1 limitations

- Incident, log, and deployment data are held in Python fixtures rather than an
  operational data store.
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

Compose still allows PostgreSQL to be started by itself for host-based backend
development. The separate `api` service is the first Phase 6.1 application
container; it is not required for the retrieval examples in this section.

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
operation to attach related knowledge to its result. The default deterministic
fake remains evidence-only, while model-backed reasoners receive the retrieved
runbooks through the shared `HypothesisGenerator` boundary.

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

The separate opt-in runtime check runs four mutable runtime cases three times,
including one valid root cause outside the frozen benchmark taxonomy:

```bash
RESOLVEAI_RUNTIME_PROVIDER=openrouter \
OPENROUTER_API_KEY=... \
uv run python -m evals.evaluate_runtime_reasoning \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai \
  --repeats 3
```

This command makes billable provider calls and is intentionally excluded from
CI. The ordinary test suite never calls OpenAI or OpenRouter. Phase 7.4 will keep
this Phase 7.2 check intact and add a separately frozen runtime-ingestion suite.

### Known evaluation limitations

- all ten incidents are synthetic;
- only three cases test retrieval-dependent knowledge;
- real-model behavior is nondeterministic;
- `INC-009` and `INC-010` were not perfectly stable with retrieval;
- `INC-008` did not demonstrate retrieval value;
- retrieval utility was measured only with GPT-5.6 Luna;
- request-scoped knowledge ingestion has one successful production smoke but not
  yet a repeatable frozen evaluation baseline;
- no prompt optimization, model comparison, hybrid retrieval, reranking, or
  query rewriting was performed.

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

## Phase 5 — Observability

Phase 5 used observability to answer where a synchronous investigation spent
time or failed. The final trace hierarchy emerged from measurements rather than
being designed upfront:

```text
investigation
├── retrieve_runbooks
│   ├── generate_query_embedding
│   └── query_runbooks
├── generate_hypothesis
└── verify_citations       # diagnosed path only
```

The engineering progression was:

```text
request/result only
        ↓
manual investigation tracing
        ↓
retrieval dominated fake-path latency
        ↓
embedding/database decomposition
        ↓
first-call embedding spike localized
        ↓
no optimization justified by current warm latency
```

Phase 5.1 measured retrieval at 244.482 ms of a 244.789 ms diagnosed
investigation, while another retrieval measured 19.092 ms. Retrieval therefore
dominated the deterministic-fake path, varied substantially, and was too coarse
to identify the source of that variation.

Phase 5.2 measured five sequential same-process investigations. The first query
embedding took 152.787 ms; the next four took approximately 4–8 ms. This pattern
is consistent with one-time or warm-up work in the embedding path, but the trace
does not establish the internal mechanism. Warm PostgreSQL/pgvector work measured
approximately 10–18 ms and was the largest remaining retrieval component. That
duration is not itself evidence of a performance problem, so no optimization was
introduced.

The deterministic fake's reasoning and citation spans were negligible. Those
reasoning measurements do not represent GPT-5.6 Luna or remote-provider
latency. Citation verification remains useful because it can fail independently,
not because its duration is significant.

Diagnosed and inconclusive results remain successful traces; inconclusive has no
citation span. Genuine retrieval failures mark `query_runbooks`,
`retrieve_runbooks`, and `investigation` as errors while preserving the original
exception.

No finer span decomposition, HTTP or dependency auto-instrumentation, OTLP,
Collector, metrics, Prometheus, or Grafana was justified. ResolveAI has no
sustained workload, SLO, retained telemetry backend, or recurring dashboard
question requiring those additions.

> Span granularity should increase only when an existing span becomes too coarse
> to answer a demonstrated operational question.

Phases 3 through 7.3 are complete. ResolveAI's CI passes on GitHub-hosted
runners, and the Northflank deployment passed direct and browser-level
verification for guided and runtime paths. The Phase 7.2 public runtime uses the
server-selected OpenRouter GPT-5.6 Luna reasoner; its capped provider secret,
deployment, metadata disclosure, and live inference smoke test are verified.
Phase 7.3 also passed scoped knowledge retrieval, cleanup, Evidence-only citation,
same-origin, console, guided-path, and mobile checks.

## Phase 6.2 — Continuous integration

The `CI` GitHub Actions workflow runs on every push and pull request. Its
independent `backend` and `frontend` jobs can run in parallel and automate the
same checks used locally.

The backend job uses Python 3.13 and uv 0.11.6, verifies `uv.lock`, checks Python
lint and formatting, and runs the deterministic pytest suite. The ordinary run
does not configure PostgreSQL or model credentials, so the three tests marked as
PostgreSQL integrations remain skipped.

The frontend job uses Node 24 and the pnpm 11.21.0 version declared in
`web/package.json`. From `web/`, it installs the frozen dependency graph, checks
TypeScript and ESLint, and creates the Next.js production build. The build
compiles the API rewrite but does not require FastAPI to be running.

Local checks first established that the commands work in the developer
environment. The successful GitHub-hosted `backend` and `frontend` jobs then
confirmed that the workflow can reproduce those checks on clean external
runners.

This first slice deliberately has no dependency caches, service containers,
real retrieval or model evaluation, browser end-to-end testing, Docker image
verification or publishing, deployment, or version matrices. None was required
to automate the established deterministic application checks.

## Phase 6.3 — Public portfolio deployment

The immediate deployment goal changed from AWS ECS/Fargate and Terraform to a
public hobby deployment with no ongoing hosting cost. AWS remains a useful
optional infrastructure exercise, but it is not required to demonstrate the
current ResolveAI application.

The selected Sandbox topology is:

```text
Northflank project
├── web       Next.js :3000, public HTTPS       (deployed and verified)
├── api       FastAPI :8000, private            (deployed)
└── database  PostgreSQL + pgvector, private    (ready)
```

Northflank was selected because its Sandbox allowance matches the current
two-service and one-database architecture, supports the existing Dockerfiles,
provides private project networking, and keeps the services running without an
idle-sleep cycle. The environment remains a portfolio Sandbox rather than a
production service with an uptime guarantee.

### 6.3.1 — Sandbox confirmation

The project was created on the free Northflank Sandbox plan. The intended
topology fits its two service slots and one database addon without introducing a
paid resource. Each deployment slice remains independently verifiable before
the next resource is added.

### 6.3.2 — PostgreSQL and pgvector

A private PostgreSQL addon was provisioned and initialized deliberately rather
than through an always-running setup service. The existing `database/init.sql`
enabled `vector`, created the schema and indexes, and inserted or updated the
nine frozen runbooks. The existing explicit FastEmbed population command stored
all nine 384-dimensional document embeddings. No OpenAI or OpenRouter call was
used during initialization.

The database remains private to the Northflank project. Runtime workloads use
the standard application connection string; administrator credentials are
reserved for initialization and maintenance.

### 6.3.3 — Private FastAPI service

Northflank builds the API from the repository-root `Dockerfile` and runs its
existing Uvicorn command on `0.0.0.0:8000`. Port 8000 is private, so it has no
reviewer-facing public endpoint. The database addon's standard `POSTGRES_URI` is
inherited through a runtime secret with the alias `DATABASE_URL`; no credential
is stored in source code.

Container verification established:

- the service could read all nine runbooks and nine stored embeddings;
- `GET /incidents` returned successfully;
- cold and warm `INC-001` investigations completed with the deterministic fake;
- retrieval returned three runbooks;
- the container did not restart or run out of memory.

The 512 MiB Sandbox service reached approximately 440 MiB during cold FastEmbed
initialization and then retained approximately 320 MiB for warm requests:

```text
cold peak          ~440 MiB / 512 MiB  (~86%)
warm steady state  ~320 MiB / 512 MiB  (~63%)
```

The cold margin is narrow but acceptable for the intended single-reviewer demo.
FastEmbed stays cached in the Python process, so the warm plateau is expected.
Concurrent cold initialization is not an intended Sandbox workload. No extra
workers, paid compute, keep-alive requests, or external model credentials were
introduced.

### 6.3.4 — Public Next.js and browser verification

The production Next.js container is publicly deployed and uses
`RESOLVEAI_API_URL=http://api:8000` for its server-side rewrite. The public
address is intentionally omitted from repository documentation. Browser-level
Chromium verification confirmed that all three incidents render, `INC-001`
produces the diagnosed presentation with visually distinct collected Evidence,
supporting Evidence, and retrieved reference knowledge, and `INC-003` produces
the successful inconclusive presentation. The browser observed same-origin HTTP
200 responses for the incident list and both investigation requests, with no
failed requests, page errors, material console errors, layout overlap, or
horizontal overflow. The optional `/favicon.ico` returns a non-material 404.

Phase 6.3.4, Phase 6.3, and the Phase 6 productionization milestone are complete.

## Phase 7.1 — Versioned runtime incident input

The current source and local Compose application now expose two explicit paths:

- the prepared `GET /incidents` and
  `POST /incidents/{incident_id}/investigate` fixture flow;
- `POST /runtime/investigate`, which accepts one transient version-1 bundle with
  a caller-supplied incident and 1–50 normalized Evidence items.

Runtime DTOs in `resolve_ai/runtime_input.py` are separate from fixture
`IncidentContext` values. They reject unknown fields and schema versions,
ambiguous timestamps, duplicate Evidence IDs, unsupported identifier shapes,
oversized text/detail collections, and more than 50 observations. The adapter
converts validated input to `Incident + Evidence[]`, and both fixture and runtime
paths call the same `investigate_evidence()` orchestration.

The Next.js interface provides a prepared guided-demo tab and a Runtime JSON
tab. It includes an editable novel example, explains transient retention and
external provider processing, presents diagnosed or inconclusive results with
the existing Evidence/runbook semantics, and reports client JSON errors and
server validation failures separately.

The Phase 7.1 boundary remains deliberately narrow:

- `GET /incidents` exposes three in-memory fixture incidents;
- a local user may now submit new normalized incident data, but it is not stored;
- PostgreSQL persists the frozen nine-runbook retrieval corpus and embeddings,
  not runtime incidents or investigation history;
- the guided fake reasoner recognizes two deliberately programmed evidence
  patterns;
- the runtime endpoint uses the configured real provider after Phase 7.2;
- completed results are returned to the browser and are not persisted.

The public Northflank deployment exposes this Phase 7.1 boundary and the Phase
7.2 live-model path. Both passed their corresponding browser or live-provider
smoke verification.

This is useful evaluation infrastructure, not evidence that arbitrary incidents
already work. The next major architecture therefore separates two worlds:

```text
ResolveAI
├── evaluation world
│   ├── immutable synthetic incidents and ground truth
│   ├── frozen retrieval cases and runbook corpus
│   └── repeatable deterministic and real-model comparisons
└── runtime world
    ├── user-supplied Incident and Evidence
    ├── scoped KnowledgeDocument ingestion and retrieval
    ├── fixed server-side real reasoner
    └── later: immutable InvestigationRun history
```

The evaluation fixtures, expected labels, case hashes, and benchmark corpus must
remain immutable. Runtime data must never silently enter benchmark retrieval or
change evaluation results. Both worlds should reuse the same investigation,
retrieval, structured-output, and citation-verification logic through explicit
input adapters, while benchmark-only taxonomies remain isolated.

The implemented bundle has this essential shape:

```json
{
  "schema_version": 1,
  "incident": {},
  "evidence": []
}
```

Phase 7.1 validated and normalized user-supplied Incident and Evidence data,
then investigated novel IDs without changing fixtures or benchmark inputs. It
proved generalized input rather than generalized reasoning; Phase 7.2 supplies
the fixed server-side real-model path without silently falling back to fake
reasoning.

Runtime knowledge should initially use bounded text or Markdown documents, one
embedding per document, synchronous FastEmbed generation, pgvector Top-3
retrieval, and strict corpus scoping. Chunking, queues, reranking, hybrid search,
query rewriting, a dedicated vector database, and background workers remain
unjustified until measurements show a concrete need.

The reviewer experience now has two explicit paths:

```text
Guided demo                         Runtime JSON
prepared synthetic incident        versioned incident bundle
deterministic and repeatable        server-selected live model in Phase 7.2
fast architecture tour             previously unseen transient input
```

The own-data path begins without accounts or durable retention. Phase 7.1 adds
schema, size, count, duplicate-ID, timestamp, and supported-type validation.
Phase 7.2 adds one concurrent model request, explicit reasoning/output budgets,
a 30-second provider timeout, stable 429/502/503/504 errors, provider/model
metadata, and an open runtime diagnosis taxonomy. The frozen evaluator keeps its
closed labels. No provider failure falls back to the deterministic fake.

## Phase 7.2 — Controlled real-model runtime reasoning

`RESOLVEAI_RUNTIME_PROVIDER` selects exactly one server-side adapter:

| Value | Fixed model | Required secret |
|---|---|---|
| `openrouter` | `openai/gpt-5.6-luna` | `OPENROUTER_API_KEY` |
| `openai` | `gpt-5.6-luna` | `OPENAI_API_KEY` |

The deployed Northflank configuration is OpenRouter with a key-level spend cap.
The API exposes safe metadata at `GET /runtime/reasoner`; it never returns a key.
Both adapters use Responses structured output with `medium` reasoning, a 4,000
output-token limit, 30-second timeout, and no SDK retries. Runtime model labels
are bounded normalized strings rather than members of the evaluator's frozen
enum. Citation verification still rejects any Evidence ID not present in the
submitted bundle.

The Phase 7.2 pull request passed GitHub Actions, merged into `main`, and deployed
through Northflank. A public live-provider smoke investigation completed through
OpenRouter. The runtime reported `openrouter/openai/gpt-5.6-luna`, while the
guided path retained `deterministic/evidence-only-fake-v1`. No browser key,
provider picker, automatic provider fallback, or persisted runtime input was
introduced.

Phase 7.2 exit status: complete, deployed, and live-provider verified.

## Phase 7.3 — Scoped runtime knowledge ingestion

The version-1 runtime bundle now accepts zero to five optional `knowledge_documents`.
Each document is plain text or Markdown, limited to 8,000 characters with a
20,000-character aggregate limit. Document IDs must be unique and cannot overlap
Evidence IDs.

Runtime documents use a separate PostgreSQL table keyed by a server-generated
UUID scope. FastEmbed generates all whole-document vectors before PostgreSQL
insertion, and one transaction inserts the complete set. The non-null embedding
column and transaction rollback prevent partially ready documents from becoming
retrievable. Runtime search filters by the exact unexpired scope; the unchanged
runbook search reads only the frozen `runbooks` table.

One runtime investigation receives the existing frozen Runbook Top-3 and a
separate current-scope KnowledgeDocument Top-3. The model prompt labels uploaded
documents as untrusted reference content, and deterministic citation verification
continues to accept only observed Evidence IDs. The UI displays retrieved runtime
documents separately and renders Markdown as inert text rather than HTML.

The Phase 7.3 pull request passed both required CI checks and merged into `main`.
The idempotent table addition was applied before the private API and public web
deployments. A public OpenRouter/Luna investigation retrieved unseen `DOC-901`,
returned only submitted Evidence IDs as citations, and left zero scoped rows
after completion. Guided diagnosed/inconclusive paths, same-origin traffic, a
clean browser console, and the 390px layout also passed.

Phase 7.3 exit status: complete, deployed, and production-verified.

## Phase 7.4 — Runtime evaluation slice

Phase 7.4 will measure the existing runtime-ingestion baseline before changing
retrieval. It will add a separate frozen dataset and evaluator covering relevant
and confusable document ranking, insufficient Evidence, untrusted citation
pressure, malformed bundles, cross-scope isolation, cleanup, and unchanged frozen
runbook results. The original ten investigation cases, eighteen retrieval cases,
and Phase 7.2 runtime-reasoning check remain unchanged.

The deterministic layer will report runtime-document Top-1 and Top-3 behavior,
validation rejection, scope leakage, cleanup, and frozen-corpus stability. An
opt-in capped provider layer will run three repetitions by default and report
status/root-cause accuracy, Evidence citation precision/recall, unsupported
citations, correct abstention, repeat agreement, and system failures. Provider
calls remain outside CI, and nondeterministic model misses remain measurements
rather than regression-test failures.

Phase 7.4 will not add API or UI fields, database schema, persistent runtime data,
chunking, hybrid retrieval, reranking, query rewriting, background workers, or
investigation provenance. A retrieval change requires a measured limitation from
this baseline.

## Verify

```bash
uv lock --check
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

Verify the complete local container packaging from the repository root:

```bash
docker compose config --quiet
docker compose build api web
docker compose up -d database api web
curl http://127.0.0.1:3000/api/incidents
```
