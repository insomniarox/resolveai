# Jev bounded decision experiment

> Historical evaluation record. This experiment used fixed input states without retrieval. Its scores do not measure the current application or its mutable runbook library. See [README](../README.md) for the current flow.

Run on 2026-09-21. Jev is promising for bounded cause selection in ResolveAI.
This experiment does not establish that it can replace the runtime reasoner.
The harder evidence-support task exposed both model differences and rubric ambiguity.

## Protocol

Six synthetic incident families produce 24 inputs. Four families are adapted from
the unchanged Phase 7.6 runtime contract dataset. Two newly authored families,
cache invalidation and object-storage policy rejection, form the holdout split.
All cases, answer labels, and questions were fixed before the first live request.
No prompt tuning or relabeling followed the results. Holdout means separate incident
families here, not independently authored or independently reviewed ground truth.

Each family has four variants:

- Structured JSON with observation summaries and all supplied reference documents.
- A lossless prose rendering of the same fields and values. It retains field names
  and ordering, so this tests serialization, not realistic messy operational prose.
- Paraphrased observation summaries. Other fields remain unchanged, so this is a
  limited wording test and does not remove all possible semantic shortcuts.
- No observations and a neutral incident description. References remain, but
  neither provider should diagnose an incident from reference text alone.

Both providers receive the same state, Choice instructions, and option meanings.
Each answers a cause-selection question with three candidates plus an abstention
option. Each available observation also gets an independent supports/contradicts/
insufficient question about a predefined claim. That claim is supplied equally to
both providers and need not match the selected cause. This measures evidence
assessment under an explicit hypothesis, not discovery of hypotheses or citations.

Candidates are manually authored for this controlled experiment. Answer positions
vary, but candidate order is not randomized. No automated candidate builder is
being evaluated. Expected answers never enter provider requests. Jev receives
native Choice questions; OpenRouter receives the same questions in a structured
output request. The transport and native output mechanisms necessarily differ.

There is no PostgreSQL access, retrieval, embedding, candidate generation,
remediation generation, or application UI in this slice. All supplied documents
are used directly. These results must not be presented as production end-to-end
investigation scores.

The evaluator runs two concurrent calls per input, one per provider, and proceeds
through inputs sequentially. There are 48 calls total, one trial per variant,
30-second client timeouts, and no SDK retries. OpenRouter uses medium reasoning
and a 4,000-output-token ceiling. Jev is pinned to `jev-1.13.0`; OpenRouter returned
`openai/gpt-5.6-luna`. No provider fallbacks ran.

## Results

| Metric | Jev | OpenRouter |
|---|---|---|
| Cause selection, development | 16/16 | 16/16 |
| Cause selection, holdout | 8/8 | 8/8 |
| Correct abstention | 9/9 | 9/9 |
| Evidence relation, development | 22/27 | 26/27 |
| Evidence relation, holdout | 9/12 | 12/12 |
| Evidence relation, all | 31/39 | 38/39 |
| False diagnoses on abstention inputs | 0/9 | 0/9 |
| Provider/output failures | 0/24 | 0/24 |
| Cause agreement across three evidence-present variants | 6/6 families | 6/6 families |
| All-answer agreement across those variants | 5/6 families | 5/6 families |
| Median request duration | 710.86 ms | 1,711.325 ms |
| Observed duration range | 645.8–879.74 ms | 1,184.59–4,607.34 ms |
| Provider-reported input tokens | 29,629 | 23,156 |
| Provider-reported output tokens | 2,868 | 2,811 |

Jev's median was about 2.4 times faster in this run. Durations include client
construction, network time, provider execution, and local validation. They exclude
retrieval and UI work. These are 24 correlated variant trials from six families,
not 24 independent incidents. There are no repeated trials, reliable tail-latency
estimates, or calibrated confidence conclusions. Token counts are provider-native
and are not directly interchangeable.

The constant abstention baseline scores 9/24 on causes. Constant "insufficient"
scores 18/39 on evidence relations. These simple controls expose class balance;
they are not competitive semantic baselines. The guided fake reasoner has no
rules for these incident families, so it is not used as a general benchmark rival.

OpenRouter reported a total cost of $0.00868365 in response usage. Jev reported
tokens but no billed cost. At the public input-token rate of $0.042 per million,
the Jev usage would cost approximately $0.001244418. That is an estimate, not a
verified beta-account charge. The original JSONL summary leaves cost null;
OpenRouter's per-call reported cost remains available in each raw usage record.
Pricing source checked on 2026-09-21: [TypeSafe models](https://docs.typesafe.ai/models).

## Disagreements and rubric limits

Jev disagreed with eight frozen evidence-relation labels:

- Stale signing revision, first observation: structured and prose versions return
  insufficient; paraphrasing changes the answer to supports.
- Idle transaction, second observation: all three versions return insufficient
  against the claim that an idle transaction holds a blocking row lock.
- Storage rejection, first observation: all three versions return contradicts
  against a missing-container claim, although the observation only establishes
  completed rendering and a request reaching storage.

OpenRouter disagreed once: the paraphrased idle-transaction observation also
returns insufficient.

The idle-transaction rubric deserves independent review. Its label is supports,
but the question says to assess that observation alone. Being idle does not by
itself establish ownership of a lock; ownership occurs in another observation.
Thus the frozen 31/39 and 38/39 scores measure agreement with the original labels,
and cannot all be attributed to model errors. We retain the labels and raw answers
rather than improving scores after the run. A revised rubric should separate
support for a subclaim from evidence for the complete causal relationship, and
use a separately frozen dataset version.

The missing-evidence variants are easy abstention controls. Only one original
family tests ambiguity with evidence still present. Reference text often explains
the correct mechanism directly, and the new holdout cases are also explicit.
The next evaluation should add partial evidence, unfamiliar wording, no matching
candidate, and plausible distractors. Candidate ordering should vary too.

## Decision

Proceed with a second bounded evaluation after reviewing the evidence rubric.
Jev's cause selection and latency justify further testing. The current experiment
is too small and explicit to justify a full parallel investigation UI or automatic
evidence acceptance. Reference-applicability selection, citation precision/recall,
open-ended candidate construction, and generated remediation remain untested.

## Reproduce and inspect

- Dataset: [jev_decision_cases.json](jev_decision_cases.json).
- Runner: [evaluate_jev_decisions.py](evaluate_jev_decisions.py).
- Raw requests, expected answers, responses, usage, and measurements:
  [jev_decision_results.jsonl](jev_decision_results.jsonl).
- Credential-free tests: [test_jev_decision_evaluation.py](../tests/test_jev_decision_evaluation.py).

The dataset SHA-256 is pinned in the evaluator and retained in the result manifest.
Output files are exclusively created and never overwritten. Failed attempts stay
in accuracy denominators and retain exception types without potentially sensitive
error messages. Confidence distributions from Jev are preserved in raw output;
they are not treated as accuracy or compared to self-reported generative confidence.

```bash
uv run python -m evals.evaluate_jev_decisions --output /tmp/jev-requests.jsonl
uv run python -m evals.evaluate_jev_decisions --live --max-calls 48 \
  --output /tmp/jev-live-results.jsonl
```

Verification: uv lock check, Ruff lint and formatting, and ordinary pytest passed
with 116 passed and 6 skipped. PostgreSQL and frontend checks were not needed for
this evaluator-only change. The 48 live calls ran separately from tests.

Archived JSONL SHA-256:
`445956b304092ae9553fb7d9d970725a25ed45dcba552e2a3856d0bd64978745`.
