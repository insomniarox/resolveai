# ResolveAI code study

This guide is for learning the repository well enough to explain it without
notes. It follows data through the system instead of following the order in
which phases were built.

Do not begin with the 1,157-line runtime ingestion evaluator. That file combines
dataset validation, PostgreSQL setup, safety checks, repeated provider calls,
metrics, and reporting. It makes the project look more complicated than the
application is.

The production backend is about 2,900 lines. The frontend application and CSS
are about 3,100 lines. Evaluators add about 2,500 lines, and backend tests add
about 3,600. Read the production path first, then use tests to challenge your
understanding, and leave the evaluators until the core concepts are settled.

## How to use this guide

For each study block:

1. Read the named files in order.
2. Follow one concrete value, usually `INC-001`, `LOG-001`, or a runtime
   Evidence ID.
3. Run the targeted tests before changing anything.
4. Answer the questions without looking at the code.
5. Write a five-line explanation in your own words.

The tests are executable documentation. A useful habit is to predict the result
of one test, run it with `-vv`, and explain why each assertion belongs at that
boundary.

## The dependency compass

Keep this small map nearby:

```text
models
  ^
  |
fixtures -> investigation <- runtime_input
                 ^               |
                 |               v
          fake or live      runtime_investigation
             reasoner             |
                 ^                v
                 |        investigation_runs
                 +----------- api
                                |
                                v
                         Next.js API client
                                |
                                v
                         React workspaces
```

Retrieval sits beside the reasoner boundary:

```text
investigation -> embeddings -> PostgreSQL and pgvector
```

Evaluators import the same domain, retrieval, and reasoning functions. Product
code never imports an evaluator.

## Study block 0: establish the shape

Read:

1. `pyproject.toml`
2. `compose.yaml`
3. `database/init.sql`
4. `resolve_ai/__init__.py`
5. `.github/workflows/ci.yml`

Learn these facts:

- Python 3.13 and uv own the backend dependency graph.
- PostgreSQL holds nine frozen runbooks, scoped runtime documents, and one-hour
  saved-run snapshots.
- pgvector performs cosine-distance ordering inside PostgreSQL.
- FastAPI, Next.js, and PostgreSQL are separate containers.
- CI runs deterministic backend tests without a provider key or PostgreSQL
  integration database. It also typechecks, lints, and builds the frontend.

Questions to answer:

- Which database rows are benchmark data?
- Which rows may contain user-submitted text?
- Why are embeddings populated outside API startup?
- Why does Next.js need its API destination at build time?

Useful commands:

```bash
docker compose config --quiet
uv lock --check
```

## Study block 1: domain data and the deterministic path

Read:

1. `resolve_ai/models.py`
2. `resolve_ai/fixtures.py`
3. `resolve_ai/reasoning.py`
4. `resolve_ai/fake_model.py`
5. `tests/test_fixtures.py`
6. the fake-model tests in `tests/test_investigation.py`

Trace `INC-001`:

```text
IncidentContext
  -> Incident
  -> LOG-001 database timeout
  -> DEP-001 pool reduction
  -> Hypothesis
  -> connection_pool_exhaustion
```

The important distinction is between raw fixture records and normalized
Evidence. `LogEntry` and `Deployment` describe source-specific records.
`Evidence` is the common reasoning input. The fake sees Evidence only. It cannot
look up an answer by incident ID.

The fake supports two causes. Everything else raises
`InsufficientEvidenceError`. That exception means the investigation reached an
honest inconclusive outcome. It does not mean the application failed.

Questions to answer:

- Why is `Hypothesis` different from `Diagnosis`?
- Why does the fake inspect the latest pool change?
- Why does `RootCauseName` allow more labels than `RootCauseLabel`?
- What would happen if a later deployment restored the connection pool?

Run:

```bash
uv run pytest tests/test_fixtures.py tests/test_investigation.py \
  -k 'fake_model or fixtures' -vv
```

## Study block 2: orchestration, retrieval, and citation verification

Read:

1. `resolve_ai/investigation.py`
2. `resolve_ai/embeddings.py`
3. `resolve_ai/retrieval.py`
4. `tests/test_investigation.py`
5. `tests/test_embeddings.py`
6. `tests/test_retrieval.py`

Start at `investigate_incident()`, then move to `investigate_evidence()`. The
first function adapts prepared fixtures. The second function is the shared
workflow used by prepared and runtime input.

The workflow does five things:

1. Copy caller-owned input.
2. Build one deterministic query.
3. Retrieve frozen runbooks and optional runtime documents.
4. Ask the selected reasoner for a hypothesis or abstention.
5. Verify cited Evidence IDs before constructing the result.

`verify_hypothesis()` checks citation existence. It does not prove that the
cited facts logically entail the diagnosis. The evaluators measure that harder
question separately.

Read the SQL strings in `retrieval.py`. They are part of the application logic.
Notice the deterministic tie-break on document ID and the exact scope predicate
for runtime knowledge.

Questions to answer:

- Why do retrieval failures propagate instead of returning inconclusive?
- Why are runbooks and runtime documents passed together to the reasoner but
  returned in separate lists?
- At what point does a pgvector score become a Python float?
- What stops a model from citing `RUN-001` or a runtime document ID?

Run:

```bash
uv run pytest tests/test_investigation.py tests/test_embeddings.py \
  tests/test_retrieval.py -q
```

With PostgreSQL running, inspect the real search:

```bash
docker compose up -d database
uv run python -m resolve_ai.populate_runbook_embeddings \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai
uv run python scripts/check_db.py
```

## Study block 3: runtime input and live reasoning

Read:

1. `resolve_ai/runtime_input.py`
2. `resolve_ai/openai_model.py`
3. `resolve_ai/openrouter_model.py`
4. `resolve_ai/runtime_reasoner.py`
5. `tests/test_openai_model.py`
6. `tests/test_openrouter_model.py`
7. `tests/test_runtime_reasoner.py`

`RuntimeIncidentBundle` is the public trust boundary. Pydantic rejects unknown
fields, unsupported schema versions, duplicate IDs, ambiguous timestamps, and
oversized input before retrieval or inference starts. `to_domain()` then creates
the same `Incident`, `Evidence`, and `KnowledgeDocument` models used by the core.

The OpenAI adapter has two schemas. The frozen benchmark schema restricts labels
to six known causes. Runtime reasoning accepts any bounded snake-case label.
Both schemas require a complete diagnosis or a fully empty inconclusive result.

OpenRouter reuses the OpenAI structured-output implementation with a different
base URL and model name. `runtime_reasoner.py` selects one configured callable
and returns safe metadata beside it.

Questions to answer:

- Which validation happens before a provider call?
- Why does runtime reasoning use an open label set?
- How does the prompt separate Evidence from untrusted reference text?
- Why is there no automatic fallback between providers?

Run:

```bash
uv run pytest tests/test_openai_model.py tests/test_openrouter_model.py \
  tests/test_runtime_reasoner.py tests/test_runtime_evaluation.py -q
```

## Study block 4: execution, cleanup, persistence, and HTTP

Read:

1. `resolve_ai/runtime_investigation.py`
2. `resolve_ai/investigation_runs.py`
3. `resolve_ai/api.py`
4. `tests/test_investigation_runs.py`
5. `tests/test_api.py`

`execute_runtime_investigation()` is the shared runtime operation. Both the
transient and saved endpoints call it. It captures timing and retrieved
references, maps known exceptions to stable failure codes, and attempts scoped
document deletion in `finally`.

Cleanup is best effort. If immediate deletion fails, expired rows cannot be
retrieved and a later ingestion purges them. This is a bounded hobby-project
trade-off, not a guarantee that no stale row can ever remain.

Saved runs are immutable JSONB snapshots. The plaintext capability returns once.
PostgreSQL stores its SHA-256 digest. Read and delete require both the public UUID
and the bearer capability.

Study the nested `try` blocks in `create_runtime_run_endpoint()`. The semaphore
protects the provider call, not the database write. A known execution failure can
be saved as a stable failed snapshot. A storage failure returns 503 and does not
pretend a run exists.

Questions to answer:

- Which exceptions become public runtime failure codes?
- Which exceptions still propagate as unexpected system failures?
- Why does the saved endpoint record a reasoner failure while the transient
  endpoint translates it directly to HTTP?
- How does the API avoid revealing whether a run ID exists?
- What does the process-local semaphore fail to coordinate across replicas?

Run:

```bash
uv run pytest tests/test_investigation_runs.py tests/test_api.py -q
```

## Study block 5: browser contract and guided UI

Read:

1. `web/lib/types.ts`
2. `web/lib/api.ts`
3. `web/app/layout.tsx`
4. `web/app/page.tsx`
5. `web/components/investigation-mode-workspace.tsx`
6. `web/components/investigation-workspace.tsx`
7. `web/components/incident-list.tsx`
8. `web/components/investigation-result.tsx`
9. the three Evidence and knowledge list components

TypeScript types disappear at runtime, so `web/lib/api.ts` validates every API
response with explicit type guards. This duplicates part of the Pydantic schema.
The duplication is tedious but intentional. The browser does not trust a network
response merely because the editor has a TypeScript interface.

The guided workspace has separate state for incident loading and investigation
execution. Follow how network, HTTP, and invalid-response failures produce
different user messages.

Questions to answer:

- Why are `DiagnosedInvestigationResult` and
  `InconclusiveInvestigationResult` a discriminated union?
- Which checks in `isInvestigationResult()` repeat server guarantees?
- Why does the UI show all collected Evidence and mark only the cited subset?
- Why does the browser use same-origin `/api` paths?

Run:

```bash
cd web
pnpm run typecheck
pnpm run lint
```

## Study block 6: runtime UI and saved comparison

Read:

1. `web/lib/runtime-bundle.ts`
2. `web/components/runtime-bundle-editor.tsx`
3. the three runtime form components
4. `web/components/runtime-investigation-workspace.tsx`
5. `web/components/runtime-run-comparison.tsx`
6. the saved-run functions in `web/lib/api.ts`
7. `web/app/globals.css`

The runtime editor owns a typed `RuntimeIncidentBundle`. Form fields update that
bundle directly. The JSON tab holds a temporary text draft, and Apply JSON
replaces the typed bundle only after parsing and bounded validation succeed.
Submitting the form normalizes browser-local timestamps, then sends the same
version-1 contract used by API callers.

Text and Markdown attachment remains a browser adapter, not a second ingestion
API. `File.text()` creates ordinary `knowledge_documents`, and the existing
runtime endpoint handles their embedding, scoped retrieval, and cleanup.

The runtime workspace keeps at most two capabilities in React state. A refresh
loses them. Saving a third run requires deleting an existing run first. These are
deliberate limits that avoid accounts and browser persistence.

The comparison component compares exact stored values. It does not judge whether
two diagnosis paragraphs mean the same thing. That restraint matters because
the live evaluations found stable causal prose with unstable raw labels.

Read CSS by section, not selector by selector. Start with the root variables,
layout grids, runtime form, comparison cards, result sections, then the 860px and
600px media queries. The file is long because all component styles share one
stylesheet. There is no CSS framework to learn.

Questions to answer:

- Where are capability tokens stored in the browser?
- Why does invalid JSON stay separate from the typed form bundle?
- At what point does an attached file become a knowledge document?
- What prevents comparing runs for two different incident IDs?
- Which comparison signals are exact and which field remains for human review?
- Why must a production API rewrite change trigger a frontend rebuild?

Run:

```bash
cd web
pnpm run test
pnpm run build
```

## Study block 7: evaluations and frozen data

Read the evaluators in this order:

1. `evals/evaluate_lexical_retrieval.py`
2. `evals/evaluate_semantic_retrieval.py`
3. `evals/evaluate_investigations.py`
4. `evals/evaluate_runtime_reasoning.py`
5. `evals/evaluate_runtime_contract.py`
6. `evals/evaluate_runtime_ingestion.py`

Read each adjacent JSON file before its evaluator. The JSON declares inputs and
ground truth. The Python code validates those declarations, executes the shared
application functions, records failures without hiding them, and calculates
metrics with explicit denominators.

`evaluate_runtime_ingestion.py` is last because it is the broad safety suite. It
checks malformed input, scoped retrieval, concurrent isolation, cleanup, frozen
runbook stability, repeated provider reasoning, attempted citations, accepted
citations, and retained rows.

`evaluate_runtime_contract.py` reuses its case and reasoning runner. It adds four
frozen pressure cases and keeps causal prose for a label-hidden review. The
project owner marked every causal facet correct across eight diagnosed outputs
and found no forbidden claims.

Questions to answer:

- Which files have SHA-256 guards?
- Why does exact-label accuracy remain visible when it is known to be brittle?
- Why can citation precision be unavailable for a wrong exact label?
- Which metrics are quality measurements and which are safety gates?
- Why must runtime data never enter the frozen runbook table?

Run deterministic evaluator tests:

```bash
uv run pytest tests/test_retrieval_evaluation.py \
  tests/test_semantic_retrieval_evaluation.py \
  tests/test_investigation_evaluation.py \
  tests/test_runtime_ingestion_evaluation.py \
  tests/test_runtime_contract_evaluation.py -q
```

Run real PostgreSQL integration tests separately:

```bash
TEST_DATABASE_URL=postgresql://resolveai:resolveai@localhost:5432/resolveai \
  uv run pytest -m integration -q
```

Do not run a live evaluator merely to understand it. Provider calls cost money
and introduce variable outputs. Read the saved reports first.

## Study block 8: packaging, tracing, and deployment

Read:

1. `resolve_ai/telemetry.py`
2. `Dockerfile`
3. `web/Dockerfile`
4. `.dockerignore`
5. `web/.dockerignore`
6. `compose.yaml`
7. `.github/workflows/ci.yml`

Then run the complete local path and draw the network:

```text
browser :3000 -> Next.js /api rewrite -> FastAPI :8000 -> PostgreSQL :5432
```

The tracing module installs one process-wide console exporter only when
`RESOLVEAI_TRACE_CONSOLE=1`. The investigation and retrieval modules create the
spans. The telemetry module does not know domain details.

Questions to answer:

- Which files enter each Docker build context?
- Why does the API container not need a database readiness script at startup?
- Which checks run in CI and which require local infrastructure?
- Why are the API and database private in the hosted topology?

## Test map

Use this map when a behavior is unclear:

| Concern | Best test file |
|---|---|
| Prepared data copies and ordering | `tests/test_fixtures.py` |
| Core workflow, fake reasoning, and citations | `tests/test_investigation.py` |
| HTTP input and failure contracts | `tests/test_api.py` |
| Embedding conversion | `tests/test_embeddings.py` |
| SQL retrieval, vector validation, and scopes | `tests/test_retrieval.py` |
| Live model structured output | `tests/test_openai_model.py`, `tests/test_openrouter_model.py` |
| Provider selection | `tests/test_runtime_reasoner.py` |
| Saved capabilities and expiry | `tests/test_investigation_runs.py` |
| Frozen investigation metrics | `tests/test_investigation_evaluation.py` |
| Runtime ingestion safety | `tests/test_runtime_ingestion_evaluation.py` |
| Phase 7.6 causal contract | `tests/test_runtime_contract_evaluation.py` |
| Trace outcome semantics | `tests/test_telemetry.py` |
| Runtime form conversion and attachment limits | `web/lib/runtime-bundle.test.ts` |

## Where the code is dense

Three areas deserve extra patience.

`evals/evaluate_runtime_ingestion.py` is large because it is a complete frozen
evaluation program, not because the runtime calls it. Splitting it could improve
navigation, but a refactor should preserve every artifact hash and metric.

`web/lib/api.ts` mirrors backend response validation. A schema generator could
remove duplication, but it would add build machinery and make the contract less
visible. For this project I would keep the explicit guards.

`web/app/globals.css` is longer than any React component. It contains repeated
component patterns and a few declarations that could be merged. Cleaning it is
reasonable after the study pass, but a CSS architecture migration would add
more concepts than value.

## Limits worth remembering

These are the design edges most likely to come up in a review:

- The workflow is synchronous and one API process accepts one live reasoner call
  at a time.
- The semaphore is process-local. Multiple API replicas would each accept one
  call.
- Immediate runtime-document cleanup is best effort. Expiry and later purge are
  the fallback.
- Saved-run expiry uses opportunistic deletion, not a scheduler.
- Citation verification checks identifier existence, not causal entailment.
- Runtime labels are preserved raw and are not stable equality keys.
- The browser manually mirrors backend response types.
- The benchmark is synthetic and too small for broad reliability claims.

These limits are acceptable for a showcase. Solving all of them would turn the
project into a platform and make the code harder to explain.

## Completion check

You understand the repository when you can explain these without opening a file:

1. How prepared and runtime inputs converge on `investigate_evidence()`.
2. Why Evidence and retrieved knowledge have different types and UI sections.
3. How a hypothesis becomes a verified diagnosis.
4. How inconclusive differs from provider or database failure.
5. How runtime documents are scoped, retrieved, and cleaned up.
6. How the provider adapter enforces a coherent structured decision.
7. How saved-run capabilities work without accounts.
8. Why the browser validates responses despite TypeScript types.
9. How frozen data, deterministic tests, PostgreSQL tests, and live baselines
   answer different questions.
10. Why Phase 7.6 did not trigger a retrieval rewrite or label service.

If any answer feels fuzzy, return to the matching study block and one targeted
test. Do not reread the entire repository.
