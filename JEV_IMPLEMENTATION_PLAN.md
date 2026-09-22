# Jev implementation plan

Updated 2026-09-22. Work remains on `feature/jev-bounded-evaluation`.
The owner reviewed the first evaluation and authorized harder cases and product
implementation. Existing uncommitted files must be preserved. Do not deploy,
commit, or push without a corresponding request.

## Intended outcome

Add a Compare models workspace that submits one incident and a bounded set of
candidate hypotheses, retrieves reference material once, and runs OpenRouter and
Jev concurrently. Show independent results, timing, usage, evidence, and failures.
Accuracy is assessed only on frozen evaluation cases, never inferred from native
confidence on a new incident.

Jev cannot generate an unrestricted diagnosis. The first product comparison
therefore makes candidate hypotheses explicit, supplied by the user. Both routes
receive the same candidates and facts. Code formats the selected hypothesis;
remediation remains a human decision. Automatic hypothesis extraction and
unrestricted generated diagnoses are outside this hobby project's scope. The existing guided,
single-provider runtime, and saved-run paths remain available.

## Steps and acceptance checks

- [x] 1. Freeze harder cases in a new dataset. Include partial evidence, incorrect
  candidates, conflicting observations, unrelated noise, negation, instruction
  injection in reference text, and changed candidate ordering. Use atomic claims
  and document interpretive edge cases in their support labels; never alter first-slice artifacts.
- [x] 2. Run a capped paired live evaluation. Preserve every request, response,
  failure, timing, usage, dataset hash, and prompt version. Report per-pressure
  failures and state the limits of the experiment. Do not tune labels afterward.
- [x] 3. Implement a typed production decision boundary. Native Jev Choice calls
  and OpenRouter structured responses use equivalent questions. Select a cause,
  then assess evidence for that selected cause with the full evidence context.
  Abstain when no candidate is established or none has supporting observations.
  Keep SDK retries disabled, secrets server-side, bounded candidates, and safe
  error codes. Expose measured usage and native confidence with its meaning.
- [x] 4. Add shared preparation and a comparison coordinator. Validate once,
  ingest scoped documents once, retrieve once, copy inputs for both branches,
  execute concurrently, and clean up once. Keep each provider failure independent.
  Use the existing process-local admission gate to bound simultaneous live work.
- [x] 5. Add comparison metadata and a POST API. Return typed streamed events for
  preparation, branch completion, and final metrics so one result can render
  before the other finishes. Keep results transient; allow JSON download. Ensure
  cleanup and gate release on errors/disconnect. No saved-comparison database.
- [x] 6. Build Compare models workspace using the existing runtime editor and a
  candidate-hypothesis editor. Design an aligned two-route timeline and evidence
  comparison; show latency, usage, outcomes, unknown accuracy, and safe failures.
  Preserve input on failure and identify stale results after edits. Validate all
  browser response boundaries, support keyboard use and narrow screens.
- [x] 7. Revise shared visual tokens and application header. Use blue and plum
  provider identity, quiet cool panels, legible body text, and monospaced timing.
  Spend visual emphasis on the shared timeline, not decorative stat cards.
- [x] 8. Test meaningful boundaries: actual overlap, isolated identical inputs,
  no answer leakage, partial failure, abstention, invalid IDs, cleanup, admission
  release, stream parsing, and output download. Run lock/Ruff/pytest, real
  PostgreSQL integration checks for preparation changes, frontend tests/typecheck/
  lint/build, and desktop/mobile browser inspection.
- [x] 9. Update README, docs/code-study.md, docs/case-study.html, .env.example,
  mds/PROJECT.md, mds/PROMPT.md, and mds/STATUS.md. Keep benchmark reports separate,
  show measured limits, and update this checklist with exact remaining work.

## Resume notes

First slice: 48 completed live calls; both models 24/24 cause selection and 9/9
abstention. Evidence-label agreement Jev 31/39 and OpenRouter 38/39 has documented
rubric ambiguity. See `evals/jev_decision_report.md`. This does not validate
unrestricted diagnosis, arbitrary candidate generation, or automatic remediation.

All nine steps are complete for the bounded comparison feature. Before resuming,
inspect `git status`, this plan, and `mds/STATUS.md`. Keep all old frozen datasets
and results unchanged.

## Completed evidence

- Harder dataset: ten families, two candidate orders, 40 live calls. Both models
  selected the expected cause on 20/20 inputs and abstained on 10/10. Atomic
  evidence-label agreement: Jev 38/42, OpenRouter 41/42. See the pressure report
  for the remaining distinctions between direct and inferred contradiction.
- Production protocol: both models reached the expected final outcome on 10/10
  reused pressure families, with 15 calls each. This is regression coverage, not
  a new holdout. `evals/comparison_protocol_results.jsonl` preserves every result.
- Product smoke: real PostgreSQL retrieval, two live providers, four calls,
  independent streamed results, JSON download, and stale-input notice verified.
- Backend: 126 tests passed, 7 integration tests skipped in the ordinary suite.
  The separate PostgreSQL run passed all 7 integration tests.
- Frontend: 13 tests passed; typecheck, lint, and production build passed.
  Desktop and mobile inspection passed. The final mobile layout adjustment used
  a mocked stream to avoid repeating live calls solely for visual checks.
- Lock check, Ruff lint/format, diff whitespace, Compose configuration, old-artifact
  hashes, and HTML anchor checks passed.

## Frontend follow-up

Frontend follow-up on 2026-09-22: aligned Compare models with the existing panel,
form, typography, and sidebar layout; removed its collision with saved-run outcome
styles. Added ten selectable synthetic incident packages, each with seven
observations, two reference documents, and four hypotheses, plus the original
invoice example. Complete input JSON and the server-derived JSON Schema can be
downloaded. Reference details now show retrieval scores and explain that similarity
ranks context, while both models assess every observation. These examples are not
new model benchmarks. Existing evaluation artifacts remain unchanged.

Follow-up verification: 15 frontend tests passed, plus lint, typecheck, and the
production build. Package contract/context-budget and comparison tests passed
11 tests with 1 integration test skipped. Docker Playwright checked all ten loads,
input/schema/result downloads, submission, reference scores, stale results,
partial failure, editor reset, and desktop/mobile rendering with mocked providers.
No additional live model calls were made.

## Deferred work and continuation steps

These are outside the completed bounded feature, not hidden implementation gaps.

1. Closed as out of scope on 2026-09-22: candidate coverage review, domain-specific
   candidate guardrails, and automatic candidate preparation. The supplying firm
   is responsible for suitable hypotheses, accurate observations, and validated
   runbooks. Existing application input validation remains in place.
2. Closed as out of scope on 2026-09-22: further model-capability evaluation,
   including an independent full-context evidence-labeling benchmark. This hobby
   project retains its existing evaluation results and application-contract tests.
   Atomic test scores still do not establish production evidence precision or
   recall; that limitation is documented, not pending work.
3. If paired persistence is wanted, design an explicit immutable snapshot using
   the existing capability and retention rules. Downloads currently provide
   transient provenance without adding a database model.
4. No deployment has been performed. A deployment needs TYPESAFE_API_KEY on the
   private API service and rebuilt API/web images. There is no schema migration.
5. The owner authorized committing and pushing the completed feature on
   2026-09-22. The complete diff was reviewed, including preserved earlier changes.
   Pre-commit verification passed 128 backend tests with 7 integration skips,
   lock consistency, Ruff lint/format, diff whitespace, and Compose configuration.
   Frontend and browser verification is recorded above. Deployment remains a
   separate step; no deployment has been performed.
