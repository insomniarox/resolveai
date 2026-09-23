# Jev comparison implementation record

The bounded comparison feature was completed in September 2026. This file records the design decision; it is no longer an implementation checklist. Read [README.md](README.md) for current behavior and [the HTML case study](docs/case-study.html#model-comparison) for the request flow. Historical results remain in [the decision report](evals/jev_decision_report.md) and [the pressure report](evals/jev_pressure_report.md).

Jev chooses from candidate hypotheses supplied by the user. It does not generate an unrestricted diagnosis here. OpenRouter receives the same incident, observations, retrieved references, and candidates. Preparation and retrieval happen once; provider branches run concurrently and report independently. The first call chooses a candidate or "none." If a candidate is selected, the second call evaluates all observations against it. The second stage depends on the first answer. A one-call design could ask about every candidate, at the cost of unused judgments.

The coordinator keeps results transient, streams each branch, and cleans up request-scoped documents. Each branch permits at most two provider calls with no SDK retries. A "none" answer needs only one call. The application reports provider usage and a separate Jev cost estimate, but does not infer accuracy from confidence or token count.

The original decision and pressure evaluations used fixed synthetic datasets and the earlier nine-runbook corpus. The live runbook library now contains 15 synthetic seeds plus explicit uploads. Those changes can affect retrieval, so archived scores are not measurements of the current mutable library. No production accuracy benchmark has been established.
