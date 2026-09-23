# ResolveAI code study

This guide follows one incident through the current code. Use [the HTML case study](case-study.html) for diagrams and worked examples, and [README.md](../README.md) for setup and Northflank seed updates. The reports in `evals/` preserve dated experiments; they do not describe the current mutable runbook corpus.

## Start with the domain boundary

Read `resolve_ai/models.py`, then `resolve_ai/fixtures.py` and `resolve_ai/investigation.py`. A prepared incident starts as logs and deployments. Collectors turn them into `Evidence`. A runtime incident arrives with its observations already normalized; `resolve_ai/runtime_input.py` validates the public bundle and converts it to the same domain types.

`Evidence` is the only source of citable observations. `RetrievedRunbook` and `RetrievedKnowledgeDocument` provide background context. `verify_hypothesis()` checks that cited IDs belong to the collected Evidence, but it cannot prove a model's explanation. `resolve_ai/fake_model.py` is a deterministic control for the guided path. It ignores retrieved text. The live reasoners use references.

For a concrete trace, start with `INC-001` in `fixtures.py`. Follow one timeout log and the pool-size deployment change through collection, query construction, the fake hypothesis, and citation checking. Compare with `INC-003`, which ends inconclusive.

## Follow reference retrieval

Read `build_runbook_query()` in `resolve_ai/investigation.py`. It joins the incident title, description, and every observation summary in order. It does not append the service, timestamps, or structured detail fields to the search query. The reasoner later receives the full incident and observations.

`resolve_ai/embeddings.py` uses FastEmbed's `BAAI/bge-small-en-v1.5` model. It embeds each whole runbook as `Title: …\n\nContent: …`, and creates a query embedding from the incident text. Both vectors have 384 values. `resolve_ai/retrieval.py` sends the query vector to PostgreSQL. The runbook SQL orders rows with non-null embeddings by ascending cosine distance, breaks ties by ID, and applies `LIMIT 3`. The displayed similarity is `1 - distance`. There is no service filter, minimum score, chunking, or reranker. Three means the three most similar *searchable* rows, not necessarily three relevant or correct procedures.

Attached documents use the same query but a separate SQL search limited to the current request's scope, expiry window, and three results. Up to three runbooks and three documents can therefore reach a reasoner. The two groups are not globally reranked. Retrieval similarity ranks references; it never removes an observation or supplies a diagnosis confidence score.

`resolve_ai/runbooks.py` lists and creates persistent official runbooks. The seed in `database/init.sql` has 15 synthetic examples; uploads receive an `UPLOAD-` UUID. New uploads are embedded before insertion. The browser in `web/components/runbook-library.tsx` accepts UTF-8 Markdown or text and shows total and searchable counts. An attachment in `runtime_knowledge_documents` is temporary incident context, not an official runbook. There is no numeric reference weight. The prompts prefer applicable runbooks for procedures while requiring observations to establish a cause. **The API has no authentication on runbook creation.** Next.js forwards public `/api` requests to it, so anyone who can reach the site can submit official guidance. The code does not enforce operator identity or approval.

## Compare the reasoning paths

The ordinary runtime path goes through `resolve_ai/runtime_investigation.py`, `resolve_ai/runtime_reasoner.py`, and `resolve_ai/openai_model.py` or `resolve_ai/openrouter_model.py`. It asks one configured provider for a structured, open-ended cause. The runtime prompt treats runbooks as official procedure guidance and attachments as supplemental context, but neither overrides observed facts. `resolve_ai/investigation_runs.py` stores an immutable, one-hour snapshot only when a caller explicitly saves a run. Request-scoped documents are deleted after execution, with expiry as a fallback.

The Compare models path is in `resolve_ai/comparison.py` and `resolve_ai/comparison_reasoner.py`. `ComparisonInput` contains one runtime bundle and one to five distinct candidate hypotheses. Preparation validates and converts the bundle, stores optional scoped attachments, retrieves references once, and copies the same incident, observations, and references into independent OpenRouter and Jev branches. The references carry `official_runbook` or `attached_document` tags. Preparation rejects a serialized state-and-questions payload over 30,000 bytes before either provider is called.

Each branch proceeds in stages:

1. The **cause call** asks which one candidate the observations establish, with `none` as a valid answer. A `none` answer ends that branch inconclusive after one call.
2. For a selected candidate, the **evidence call** asks one relation question per observation: `supports`, `contradicts`, or `unrelated`. All these questions go in one provider call. Each question sees the full context and explicitly names the selected candidate.
3. Code reports a candidate as supported only if at least one observation supports it and none contradicts it. Otherwise it reports inconclusive. Provider failures are reported per branch. The shared attachment scope is cleaned up once.

The second call depends on the first call's candidate. Jev evaluates questions within one request independently, so an evidence question in the first call cannot read the cause question's answer. A one-call design could ask evidence questions for *every* candidate and use only the selected candidate's labels; it would spend tokens on discarded judgments. The current two-stage design is a tradeoff, not a requirement of the models. Both providers use at most two calls, and one if they choose `none`. The two provider branches run concurrently.

`web/components/model-comparison-workspace.tsx` renders each branch as it arrives. It shows reported token usage by input and output, provider-reported cost when available, and a separate Jev estimate for the pinned model. The optional operator reference answer stays in browser state and out of model requests. A match on one incident is not measured accuracy. Native Choice confidence is not accuracy either. The JSON download retains events for inspection, but comparisons are not saved as database runs.

## Check the transport and UI

`resolve_ai/api.py` exposes guided, runtime, saved-run, comparison, and runbook routes. The comparison response is an NDJSON stream with `prepared`, `branch`, `error`, and `finished` events. `web/lib/comparison-api.ts` validates event shapes, order, candidate bounds, and evidence IDs before the UI renders them. `web/lib/runtime-bundle.ts` prepares and validates the editor's input. `web/lib/data/comparison-packages.json` holds the ten interactive synthetic packages; they are examples, not evaluation cases.

The Next.js app rewrites `/api` to FastAPI. Northflank exposes Next.js publicly and keeps API and PostgreSQL on the private project network. The private API is reachable through the public Next.js `/api` rewrite. Runbook uploads have no authentication or approval check; the private network alone does not protect that route. See [README.md](../README.md#northflank-deployment-and-seed-updates) for seed-only updates when a PostgreSQL user cannot run the table DDL in `database/init.sql`.

## Read the evaluations as dated evidence

The [bounded Jev decision report](../evals/jev_decision_report.md) covers a small fixed set of candidate decisions. The [pressure report](../evals/jev_pressure_report.md) adds harder cases and a reused-family production-protocol regression. The [runtime contract report](../evals/runtime_contract_report.md) tests an older fixed corpus and records human review. None measures general diagnosis accuracy, the current 15-seed library, or arbitrary operator uploads. Do not revise old result artifacts to make current code appear measured.

Useful checks for the current implementation:

| Boundary | Checks |
| --- | --- |
| Core investigation and citations | `tests/test_investigation.py` |
| Retrieval and embeddings | `tests/test_retrieval.py`, `tests/test_embeddings.py` |
| Runbook storage and API | `tests/test_runbooks.py`, `tests/test_api.py` |
| Comparison calls, shared state, cleanup | `tests/test_comparison.py` |
| Browser stream and bundle parsing | `web/lib/comparison-api.test.ts`, `web/lib/runtime-bundle.test.ts` |
| Saved-run capability and expiry | `tests/test_investigation_runs.py` |

Run `uv run pytest -q` and the frontend scripts in `web/package.json` for code changes. PostgreSQL integration tests need `TEST_DATABASE_URL` pointing to a disposable database. Live provider experiments require explicit credentials and are separate from routine tests.
