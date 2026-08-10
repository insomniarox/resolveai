# ResolveAI

ResolveAI is an AI incident investigation copilot built entirely with synthetic
operational data. The current Phase 1 slice investigates synthetic connection
pool and certificate-expiration incidents using plain Python orchestration and
a deterministic fake hypothesis generator.

## Run locally

```bash
uv sync
uv run uvicorn resolve_ai.api:app --reload
```

Investigate the included incident:

```bash
curl -X POST http://127.0.0.1:8000/incidents/INC-001/investigate
curl -X POST http://127.0.0.1:8000/incidents/INC-002/investigate
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
                                            ▼
fake_model.py: generate_hypothesis()
                │ returns unverified Hypothesis
                ▼
investigation.py: verify_hypothesis()
                │ resolves cited evidence IDs
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
systems. It keeps Phase 1 runnable without a database or external integrations.

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

### 4. The fake proposes a hypothesis

`generate_hypothesis()` receives only the evidence list. It does not receive
`INC-001`, so it cannot select a canned answer by incident ID.

The current deterministic rule finds both the connection timeout and pool
reduction. It returns a `Hypothesis` containing a probable cause, confidence,
remediation, and the two evidence IDs it wants to cite.

The hypothesis is still unverified. A future LLM could cite an identifier that
does not exist, so model-shaped output is not used as the final response yet.

### 5. The application verifies citations

`verify_hypothesis()` creates a lookup from collected evidence IDs to their full
objects. It rejects the hypothesis if any cited ID is absent. For Phase 1, it
does not attempt to prove that the evidence logically guarantees the conclusion.

After this check, citation strings are replaced with their complete `Evidence`
objects and the application returns an `InvestigationResult`.

### 6. FastAPI returns JSON

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
| `tests/test_investigation.py` | Does the domain logic behave correctly by itself? |
| `tests/test_api.py` | Does the public HTTP contract behave correctly? |

## Deliberate Phase 1 limitations

- Data is held in Python fixtures rather than a database.
- The fake supports only two explicit evidence patterns.
- Confidence values are illustrative, not statistically calibrated.
- Verification checks citation existence, not whether evidence proves causality.
- Recommended actions are returned but never executed.

## Verify

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
