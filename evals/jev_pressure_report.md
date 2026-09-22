# Jev pressure cases and production protocol

Evaluated on 2026-09-21. All old datasets and result artifacts remain unchanged.

## Harder decision cases

The new frozen dataset contains ten incident families. It tests a restored
configuration, incomplete lock evidence, explicit negation, an injected instruction
inside reference text, a plausible cache distractor, a missing correct candidate,
unrelated-service observations, unresolved conflicting monitors, unfamiliar wording,
and an ambiguous HTTP 429 response. Each case runs with original and reversed
candidate order. Option keys and expected answers remain unchanged.

Evidence questions now concern atomic claims and distinguish direct affirmation,
direct contradiction, and insufficient information. This avoids asking one
observation to prove an entire multi-record causal chain. Expected answers and
questions were fixed before live calls; no labels were revised afterward.
Six families are development cases and four are designated holdout families.
They share an author and test design, so the split does not imply independent
validation. The cases are harder controls, not a representative incident corpus.

| Measurement | Jev | OpenRouter |
|---|---|---|
| Cause selection, development | 12/12 | 12/12 |
| Cause selection, holdout | 8/8 | 8/8 |
| Correct abstention with observations present | 10/10 | 10/10 |
| Evidence-label agreement, development | 22/24 | 23/24 |
| Evidence-label agreement, holdout | 16/18 | 18/18 |
| Evidence-label agreement, total | 38/42 | 41/42 |
| Provider/output failures | 0/20 | 0/20 |
| Median request time | 745.73 ms | 1,987.18 ms |
| Reported input tokens | 18,216 | 13,712 |
| Reported output tokens | 2,834 | 1,892 |

All 40 calls completed, with no retries. OpenRouter reported $0.0050128 in total
usage cost. Jev returned token usage without billed cost. Candidate-order changes
did not change either model's selected cause. They changed one OpenRouter evidence
answer. The constant abstention baseline scores 10/20 on causes.

Neither model followed the reference instruction to select the credential-failure
candidate. That is one attack text under two orderings, not a prompt-injection
robustness guarantee.

Jev classified the quota-rejection observation as contradicting invalid credentials
in both orderings; OpenRouter did so only in reversed order. The label is
insufficient because that observation does not directly report credential state.
This is still a subtle distinction between ruling out a primary explanation and
ruling out any concurrent fault. Keep the label-agreement terminology.

Jev also treated a monitor reporting revision 18 as contradicting the atomic claim
that another monitor reports revision 17. The second monitor conflicts with the
underlying system-state claim, but does not disprove the existence of the first
report. Both models nevertheless abstained on the unresolved incident diagnosis.

These results support a bounded comparison feature with explicit hypotheses and
visible uncertainty. They do not support automatic hypothesis generation or
remediation execution. Ten families with two correlated orderings do not establish
broad reliability or calibrated confidence.

## Production protocol regression

The app needs evidence associated with its selected hypothesis, rather than an
unrelated atomic test claim. The production protocol therefore uses two stages:

1. Select one candidate or abstain using all incident facts and references.
2. If selected, assess each observation's role in the selected hypothesis with the
   full incident context. Support may concern one part of a causal relationship.
   Any contradiction or absence of supporting observations produces inconclusive.

The second stage depends on the first result and is a separate call. Both models
receive the same state and equivalent Choice questions. The app copies exact
candidate text into the result, returns Evidence IDs from the supplied records,
and exposes native confidence only as a concentration measure. It does not
synthesize a new diagnosis or remediation.

A separate live regression reused all ten pressure families under this production
protocol, without order variants. Both models reached the expected final outcome
on 10/10 families. Each made 15 calls: five abstentions used one call each and five
supported cases used two calls each. No provider failures occurred. Median route
time was 1,071 ms for Jev and 2,729 ms for OpenRouter.

This reuse checks the changed implementation contract. It is not a new holdout
and does not independently validate the second-stage evidence labels. The previous
atomic label scores must not be presented as accuracy for these new evidence
questions. Backend tests cover contradiction handling, citation membership,
parallel execution, failure isolation, and shared-scope cleanup.

A final browser smoke comparison used the synthetic invoice example with real
PostgreSQL retrieval and both providers. Both supported the receipt-callback
hypothesis; Jev took 1.57 seconds and OpenRouter 3.80 seconds. Shared preparation
took 209 ms, with 4.03 seconds total wall time. Four additional provider calls ran.
These are one-run observations, not benchmark medians.

## Artifacts and reproduction

- [Frozen pressure cases](jev_pressure_cases.json)
- [Pressure evaluator](evaluate_jev_pressure.py)
- [All 40 pressure responses](jev_pressure_results.jsonl)
- [Production protocol evaluator](evaluate_comparison_protocol.py)
- [All 20 production route results, 30 calls](comparison_protocol_results.jsonl)

The pressure dataset hash is pinned in its evaluator. Each pressure record retains
the shared request fingerprint and all raw output. The production artifact records
the exact state, candidates, returned decisions, stage durations, usage, and prompt
version. Outputs are exclusively created and never overwrite previous results.

```bash
uv run python -m evals.evaluate_jev_pressure --live --max-calls 40 \
  --output /tmp/jev-pressure.jsonl
uv run python -m evals.evaluate_comparison_protocol --live --max-calls 40 \
  --output /tmp/jev-protocol.jsonl
```

Without `--live`, neither command makes provider calls. The second command reserves
40 calls as a worst-case limit even though this run needed only 30.

## Implementation verification

The bounded comparison feature passed 126 ordinary backend tests, with 7
integration tests skipped in that run. All 7 real PostgreSQL integration tests
passed separately, including shared-context retrieval, scoped cleanup, and
unchanged frozen runbooks. Frontend checks passed 13 tests, typecheck, lint, and
production build. Lock, Ruff, whitespace, Compose, and HTML-anchor checks passed.

Desktop/mobile browser inspection covered the real smoke result, download, and
stale-input notice. A mock stream verified the final mobile table adjustment
without additional provider calls. No deployment or schema migration was made.
