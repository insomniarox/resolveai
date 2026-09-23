# ResolveAI

ResolveAI is an incident investigation demo built with synthetic data. The guided path uses prepared incidents and a deterministic reasoner. The runtime path accepts a validated incident bundle and asks one configured reasoning provider for a cause. The Compare models page gives OpenRouter and Jev the same incident and user-supplied candidate causes. None of these paths takes remediation action.

Open [the HTML case study](docs/case-study.html) for the system and [the code study](docs/code-study.md) for a reading path through the implementation. The [evaluation reports](evals/) record dated experiments; their scores are not claims about the current, mutable runbook library.

## How an assessment works

The incident and observations are facts supplied to the application. Runbooks and attached documents are reference text. The app builds a search query from the incident title, description, and every observation summary. FastEmbed creates a 384-value query embedding. PostgreSQL ranks stored runbooks by cosine distance and returns up to three with embeddings; a separate query selects up to three attached documents from the current request. There is no service filter or minimum similarity threshold. Similarity describes text relevance, not the probability that a cause is correct.

Runbooks persist across incidents and are treated as operator-designated official guidance about procedures and expected behavior. Attachments provide temporary context for one request and are deleted after use, with a 15-minute expiry fallback. Both kinds of reference can inform interpretation. Observations still determine whether a cause is supported, and only observation IDs can support a diagnosis. No numeric weight is assigned to either reference type. The guided deterministic reasoner does not read retrieved text; the live paths do.

The comparison sends one prepared context to both providers concurrently. Each provider makes **one call to choose a candidate or "none"**. If it picks a candidate, it makes **one more call to classify every observation** as supporting, contradicting, or unrelated to that candidate. All observation questions in that second stage are batched into one provider call. A "none" answer stops after the first call. This two-stage design lets the second stage name the selected candidate. Jev's questions within a single request are independent and cannot see another question's answer. A one-call alternative would assess observations against every candidate and discard the unused answers. Two calls are a design choice, not a model requirement. [See the implementation](resolve_ai/comparison.py).

A candidate is reported as supported only when at least one observation supports it and none contradicts it. Otherwise the result is inconclusive. The comparison copies the candidate text; it does not generate a diagnosis or remediation. Results are transient and can be downloaded as JSON. The ordinary runtime path instead returns an open-ended, structured hypothesis and verifies that cited IDs belong to supplied observations. Citation membership does not prove the explanation true.

## Runbook library

The Compare models page lists the entire library by title and service, with total and searchable counts. Expanding a runbook shows its content. The seed contains 15 synthetic examples. The result panel separately shows the runbooks actually retrieved for that assessment.

An operator can add an official runbook by uploading UTF-8 `.md`, `.markdown`, or `.txt` or pasting text. The browser limits a file to 24 KB and the content to 6,000 characters. The API requires a nonblank title and service, embeds the text before insertion, and assigns an `UPLOAD-` UUID. Successful uploads persist and are immediately searchable. There is no approval or versioning workflow. `POST /runbooks` requires a Bearer token matching `RUNBOOK_ADMIN_TOKEN` on FastAPI. Without a configured token of at least 32 characters, uploads fail closed with 503. A missing or incorrect token returns 401. The public site can still list runbooks; the upload form asks for the token and clears it after a successful upload. The token is not stored in the incident, comparison, browser storage, or downloaded JSON.

`GET /runbooks` lists stored runbooks without a token. `POST /runbooks` accepts JSON with `title`, `service`, and `content`, plus `Authorization: Bearer <token>`. A failed embedding leaves no partial upload. The shared token controls publication, but it does not identify individual editors or review content.

## Comparison measurements

Cards show provider-reported input and output tokens summed across returned calls. A failed branch may show only partial usage. Providers can count tokens differently, and a branch that stops after one call has a different workload from one that reaches the second. Token totals alone do not establish cost or quality.

Jev returns token usage without billed cost. For `jev-1.13.0`, the app separately estimates cost from input tokens at $0.042 per million; output tokens are free. This rate was checked on 2026-09-22 against [TypeSafe's model page](https://docs.typesafe.ai/models). The estimate excludes shared retrieval and embedding work, and an unknown Jev version receives no estimate. Provider-reported cost, when present, takes precedence. The exported event keeps reported and estimated cost in separate fields.

The optional reference answer selects one candidate or "No hypothesis established." The browser compares each completed branch with that answer and reports match or mismatch. It does not send the answer to either model. One match is not an accuracy estimate. Jev's Choice confidence measures concentration among its choices, not diagnosis accuracy. Historical measured results and their limits are in the [decision report](evals/jev_decision_report.md), [pressure report](evals/jev_pressure_report.md), and [runtime contract report](evals/runtime_contract_report.md).

## Run locally

Use Python 3.13, uv, Docker with Compose, Node.js 24, and pnpm 11.21.0. The database image includes pgvector. Start PostgreSQL, initialize a new local database, embed missing seeds, and start the API:

```bash
uv sync
docker compose up -d database
docker compose exec -T database \
  psql -U resolveai -d resolveai -v ON_ERROR_STOP=1 < database/init.sql
uv run python -m resolve_ai.populate_runbook_embeddings \
  --database-url postgresql://resolveai:resolveai@localhost:5432/resolveai
DATABASE_URL=postgresql://resolveai:resolveai@localhost:5432/resolveai \
  uv run uvicorn resolve_ai.api:app --reload
```

To use live models or publish runbooks locally, copy `.env.example` to `.env` and set the required keys. Generate a runbook admin token with `openssl rand -hex 32` and set `RUNBOOK_ADMIN_TOKEN` on the API service only. Ordinary runtime inference uses `RESOLVEAI_RUNTIME_PROVIDER=openrouter` with `OPENROUTER_API_KEY`, or `openai` with `OPENAI_API_KEY`. Comparison requires both `OPENROUTER_API_KEY` and `TYPESAFE_API_KEY` on the API service. The comparison models are `openai/gpt-5.6-luna` and `jev-1.13.0`. Secrets stay server-side.

In a second terminal:

```bash
cd web
cp .env.local.example .env.local
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://127.0.0.1:3000`. Next.js forwards `/api` requests to FastAPI. The comparison editor has ten synthetic packages and an original invoice example; these are examples, not model benchmarks. Runtime bundles accept 1–50 observations and up to five temporary text or Markdown documents. Comparison accepts one to five distinct candidate hypotheses. For large inputs, its additional 30,000-byte state-and-questions limit can reject a request before either provider runs.

For the complete local container topology, run `docker compose build api web` and `docker compose up -d database api web` after database setup. The Next.js API rewrite is compiled into the web image, so changing `RESOLVEAI_API_URL` requires rebuilding that image.

## Northflank deployment and seed updates

Northflank deploys product commits on `main`. The public Next.js service talks to private FastAPI and PostgreSQL services. The database uses TLS. Configure `RUNBOOK_ADMIN_TOKEN` as a secret on the **API service** before deploying the guarded upload route. Generate it with `openssl rand -hex 32`, share it only with people allowed to publish official runbooks, and enter it in the upload form when needed. Do not set it as a public web build variable. This auth change requires an API rollout but no database change. Run the embedding command in the API container after adding seed rows:

```bash
python -m resolve_ai.populate_runbook_embeddings --database-url "$DATABASE_URL"
```

For an **existing** Northflank database, `database/init.sql` includes table DDL that may fail under a database user who does not own those tables. To refresh only the seed runbooks, forward the PostgreSQL addon with the Northflank CLI, keep that process open, and run the final `INSERT INTO runbooks` statement through `psql` using the forwarded address, database name, and credentials from the addon's Connection details. For this SQL file, the insert is its final statement:

```bash
sed -n '/^INSERT INTO runbooks /,$p' database/init.sql |
  psql "host=FORWARDED_HOST port=FORWARDED_PORT dbname=DATABASE user=USERNAME sslmode=require" \
    -W -v ON_ERROR_STOP=1
```

Use the actual address and port printed by the CLI, which may differ from local Docker's port. If the insert fails for lack of permission, connect as the table owner or with the Northflank admin credentials. The seed statement preserves unchanged embeddings and uploaded entries. Afterwards, run the embedding command above in the Northflank API container and check the library's searchable count. Applying seeds or uploading runbooks changes retrieval; historical evaluation scores used the original nine-runbook corpus.

## API and verification

The main routes are `GET /incidents`, `POST /incidents/{id}/investigate`, `POST /runtime/investigate`, `POST /runtime/runs`, `GET` and `DELETE /runtime/runs/{id}`, `GET /runtime/comparison`, `POST /runtime/compare`, and `GET` and `POST /runbooks`. Saved runs are immutable one-hour snapshots accessed by a bearer capability; there is no list or update route. The saved-run API stores only the capability hash.

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
# In web/: pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

PostgreSQL integration tests require `TEST_DATABASE_URL` and a disposable database. See [the code study](docs/code-study.md) for the relevant tests and source files.
