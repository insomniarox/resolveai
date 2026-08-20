# Phase 7.6 runtime contract report

## Scope

Phase 7.6 asks whether ResolveAI can measure causal correctness separately from
generated label wording without using an automated semantic judge. The phase
adds four preregistered synthetic cases and does not change the runtime output
schema, retrieval implementation, API, UI, database schema, or deployment.

The frozen cases cover:

- a decisive fact buried in a longer document beside a close distractor;
- near-duplicate current and obsolete document revisions;
- conflicting guidance resolved by observed Evidence;
- conflicting guidance that should produce an inconclusive result.

Dataset SHA-256:

```text
500cdffc2c50b314beb322b0cfef72167a6932f05a1828a53beac5d125e90065
```

## Deterministic PostgreSQL result

The local PostgreSQL and pgvector run on 2026-08-20 produced:

```text
Runtime-document Top-1 accuracy:       0/1 (0%)
Required-document Top-3 recall:        6/6 (100%)
Post-cleanup retained rows:              0
Frozen runbook results unchanged:      yes
Deterministic safety gates:            pass
```

The obsolete receipt-key revision ranked first, 0.0078 similarity points ahead
of the current revision. Both reached the Top-3 supplied to the reasoner. This is
a measured near-duplicate ranking weakness. It does not by itself justify a
retrieval change.

Local verification passed `uv lock --check`, Ruff lint and format checks, 107
ordinary tests with 6 skips, and all 6 real PostgreSQL integration tests. The
runtime knowledge table contained no rows after the evaluation.

## Capped live-provider result

The live baseline used OpenRouter with `openai/gpt-5.6-luna` for three repeats
over four cases, twelve calls in total:

```text
Status accuracy:                         11/12 (92%)
Exact root-cause label accuracy:           0/9 (0%)
Correct abstention:                        3/3 (100%)
Status + exact-label repeat agreement:     1/4 (25%)
Unsupported attempted citations:            0
Attempted KnowledgeDocument citations:      0
Accepted unsupported citations:             0
System failures:                             0
Post-cleanup retained rows:                  0
```

One diagnosed-expected long-document repeat returned inconclusive. The other two
repeats diagnosed the expected quota problem. Exact labels varied across every
diagnosed case even when the accepted Evidence and causal prose agreed.

Citation precision and recall remain `N/A` under the Phase 7.4 exact-label gate.
The human review below establishes causal correctness for eight diagnosed
outputs. The generated blind packet did not retain citation IDs, so citation
precision and recall cannot be reconstructed for that reviewed subset.

## Completed blind causal review

The project owner reviewed each item without consulting the full provider
output. The generated label, provider, repeat number, and case identity were
omitted. Each causal facet was marked `correct`, `absent`, or `contradicted`, and
the reviewer recorded whether the prose made a forbidden claim.

### review-43304ae99c

The rollout redirected invoice exports from tenant profile 8 to profile 12,
whose submission quota was exhausted, causing HTTP 429 responses before provider
job creation.

Expected causal facets:

- Affected component: The invoice provider tenant selected by route profile 12.
- Failure mode: Profile 12 had exhausted its daily submission quota.
- Operational effect: Invoice exports received HTTP 429 before the provider
  created a job.

Forbidden claims:

- The provider was unavailable for every tenant.
- Invoice export workers were backlogged.
- The provider credential was invalid.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

### review-49939919cd

The verifier switched to receipt key slot B but retained key revision 17, while
incoming callbacks use slot B revision 18, causing signature verification
failures.

Expected causal facets:

- Affected component: The receipt callback verifier using key slot B.
- Failure mode: The verifier loaded stale key revision 17 instead of active
  revision 18.
- Operational effect: Valid revision-18 callback signatures were rejected.

Forbidden claims:

- The callback provider was unavailable.
- The provider failed to retry callbacks.
- Slot B still legitimately used revision 17.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

### review-4e3366becb

Transaction 881 has remained idle in transaction for 180 seconds while holding
the row lock needed by seven order updates, causing the updates and a caller to
time out.

Expected causal facets:

- Affected component: Order writes waiting on the database row owned by
  transaction 881.
- Failure mode: An idle transaction retained a row lock and blocked later
  updates.
- Operational effect: Waiting order updates and a caller timed out behind the
  lock.

Forbidden claims:

- The database connection pool was undersized.
- The API timeout setting caused the blocking transaction.
- Transaction 881 had already released the lock.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

### review-500ec3972d

Invoice exports were rerouted from tenant profile 8 to profile 12, whose daily
submission quota was exhausted, causing HTTP 429 responses before provider job
creation.

Expected causal facets:

- Affected component: The invoice provider tenant selected by route profile 12.
- Failure mode: Profile 12 had exhausted its daily submission quota.
- Operational effect: Invoice exports received HTTP 429 before the provider
  created a job.

Forbidden claims:

- The provider was unavailable for every tenant.
- Invoice export workers were backlogged.
- The provider credential was invalid.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

### review-cb072ead60

The verifier switched to slot B but retained receipt key revision 17, while
callbacks are signed with slot B revision 18, causing signature verification
failures.

Expected causal facets:

- Affected component: The receipt callback verifier using key slot B.
- Failure mode: The verifier loaded stale key revision 17 instead of active
  revision 18.
- Operational effect: Valid revision-18 callback signatures were rejected.

Forbidden claims:

- The callback provider was unavailable.
- The provider failed to retry callbacks.
- Slot B still legitimately used revision 17.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

### review-d832ca6749

Transaction 881 has remained idle in transaction for 180 seconds while holding
the row lock, blocking seven order updates and causing the caller timeout.

Expected causal facets:

- Affected component: Order writes waiting on the database row owned by
  transaction 881.
- Failure mode: An idle transaction retained a row lock and blocked later
  updates.
- Operational effect: Waiting order updates and a caller timed out behind the
  lock.

Forbidden claims:

- The database connection pool was undersized.
- The API timeout setting caused the blocking transaction.
- Transaction 881 had already released the lock.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

### review-e686dc93fc

Transaction 881 has remained idle in transaction while holding the row lock,
blocking seven order updates and causing the caller timeout.

Expected causal facets:

- Affected component: Order writes waiting on the database row owned by
  transaction 881.
- Failure mode: An idle transaction retained a row lock and blocked later
  updates.
- Operational effect: Waiting order updates and a caller timed out behind the
  lock.

Forbidden claims:

- The database connection pool was undersized.
- The API timeout setting caused the blocking transaction.
- Transaction 881 had already released the lock.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

### review-e838810727

The verifier switched to slot B but retained key revision 17, while callbacks
were signed with slot B key revision 18, causing signature verification failures.

Expected causal facets:

- Affected component: The receipt callback verifier using key slot B.
- Failure mode: The verifier loaded stale key revision 17 instead of active
  revision 18.
- Operational effect: Valid revision-18 callback signatures were rejected.

Forbidden claims:

- The callback provider was unavailable.
- The provider failed to retry callbacks.
- Slot B still legitimately used revision 17.

Review:

- Affected component: `[correct]`
- Failure mode: `[correct]`
- Operational effect: `[correct]`
- Forbidden claim present: `[no]`
- Notes:

## Human-reviewed metrics

The project owner completed the blind review on 2026-08-20:

```text
Reviewed diagnosed outputs:                 8
Affected-component accuracy:             8/8 (100%)
Failure-mode accuracy:                   8/8 (100%)
Operational-effect accuracy:            8/8 (100%)
All-facets causal correctness:          8/8 (100%)
Forbidden-claim-free outputs:           8/8 (100%)
Citation precision on causal matches:   not recoverable
Citation recall on causal matches:      not recoverable
```

The two citation metrics are unavailable because the blind packet retained prose
and rubrics but omitted each output's citation IDs. The automated layer still
recorded zero unsupported attempted citations, zero attempted
KnowledgeDocument citations, and zero accepted unsupported citations.

## Decision

Phase 7.6 is complete. Human review found all three causal facets in all eight
diagnosed outputs and found no forbidden claims. The automated result rules out
an exact label as a stable semantic identity and does not establish a need to
change retrieval. ResolveAI keeps semantic Top-3, the existing runtime output
schema, raw generated labels, and no automated semantic judge. Reopen this
question only if later evidence shows required knowledge leaving Top-3 or causal
facets missing from diagnosis prose.
