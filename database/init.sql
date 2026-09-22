-- pgvector adds a fixed-dimension vector type and distance operators to the
-- same PostgreSQL database that already provides lexical retrieval.
CREATE EXTENSION IF NOT EXISTS vector;

-- Each row is one complete runbook and therefore one initial retrieval chunk.
-- The generated column keeps the searchable representation synchronized with
-- the source text without requiring Python to implement tokenization.
CREATE TABLE IF NOT EXISTS runbooks (
    id text PRIMARY KEY,
    title text NOT NULL,
    service text NOT NULL,
    content text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A')
        || setweight(to_tsvector('english', content), 'B')
    ) STORED
);

-- Embeddings are populated separately because generating them requires a model
-- outside PostgreSQL. NULL means this runbook still needs to be embedded.
ALTER TABLE runbooks
ADD COLUMN IF NOT EXISTS embedding vector(384);

CREATE INDEX IF NOT EXISTS runbooks_search_vector_idx
    ON runbooks
    USING GIN (search_vector);

-- Runtime documents live in a separate table so no benchmark query can select
-- them accidentally. A server-generated scope owns every row, and NOT NULL on
-- the embedding prevents half-ready documents from becoming retrievable.
CREATE TABLE IF NOT EXISTS runtime_knowledge_documents (
    scope_id uuid NOT NULL,
    document_id text NOT NULL,
    title text NOT NULL,
    content_type text NOT NULL CHECK (
        content_type IN ('text/plain', 'text/markdown')
    ),
    content text NOT NULL,
    embedding vector(384) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (scope_id, document_id)
);

CREATE INDEX IF NOT EXISTS runtime_knowledge_documents_expires_at_idx
    ON runtime_knowledge_documents (expires_at);

-- Saved investigations are explicit, short-lived immutable snapshots. The
-- plaintext capability is returned to the caller once; PostgreSQL keeps only
-- its SHA-256 digest. There is deliberately no owner, listing, or update path.
CREATE TABLE IF NOT EXISTS investigation_runs (
    id uuid PRIMARY KEY,
    capability_token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('completed', 'failed')),
    snapshot jsonb NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS investigation_runs_expires_at_idx
    ON investigation_runs (expires_at);

-- The corpus deliberately gives RUN-003 one lexical overlap with the test
-- query. RUN-001 should rank higher because its weighted title matches both the
-- "connection pool" phrase and "timeout", while RUN-003 has "timeout" only in
-- its lower-weight body. This demonstrates lexical ranking rather than semantic
-- judgment about which operational topic is related.
INSERT INTO runbooks (id, title, service, content)
VALUES
    (
        'RUN-001',
        'Database connection pool timeout diagnosis',
        'payment-service',
        'Use this runbook when requests fail because the service cannot acquire '
        'a database connection from its pool. Check recent pool-size configuration '
        'changes and connection acquisition timeout logs. Restore the previous '
        'pool size after approval when a deployment reduced it unexpectedly.'
    ),
    (
        'RUN-002',
        'Authentication certificate rotation',
        'authentication-service',
        'Use this runbook when clients are rejected because a certificate expired. '
        'Confirm the certificate name and expiration date, issue a replacement '
        'through the approved rotation process, and validate authentication.'
    ),
    (
        'RUN-003',
        'Notification provider outage investigation',
        'notification-service',
        'Use this runbook when an external notification provider is unavailable. '
        'Inspect provider health and request failures, confirm whether an upstream '
        'timeout is occurring, and fail over only through the approved process.'
    ),
    (
        'RUN-004',
        'Database lock contention and blocked transactions',
        'payment-service',
        'Use this runbook when requests stall because one database transaction '
        'holds row locks needed by other transactions. Inspect lock waits, active '
        'sessions, and long-running transactions to identify the blocker. Roll back '
        'or terminate the blocking transaction only after approval, then correct '
        'the transaction scope that allowed the lock to remain open.'
    ),
    (
        'RUN-005',
        'Upstream TLS server certificate validation failure',
        'payment-service',
        'Use this runbook when a service cannot establish TLS to an upstream '
        'endpoint because the server certificate is expired, untrusted, or does '
        'not match the requested hostname. Inspect the peer certificate chain and '
        'handshake validation error. Renew or correct the upstream certificate '
        'through the approved process, then retry the connection.'
    ),
    (
        'RUN-006',
        'Notification queue backlog and worker lag',
        'notification-service',
        'Use this runbook when notifications remain queued because delivery workers '
        'consume messages more slowly than they arrive. Check queue depth, '
        'oldest-message age, worker health, and processing rate while confirming '
        'the external provider remains responsive. Restore worker capacity or '
        'correct the consumer bottleneck before retrying queued messages.'
    ),
    (
        'RUN-007',
        'Payment database client profiles and admission telemetry',
        'payment-service',
        'Payment database client profile 4 provides 20 reusable sessions for '
        'interactive checkout traffic. Profile 7 provides 5 reusable sessions '
        'and is intended for low-concurrency settlement jobs. Admission state '
        'amber means every configured reusable session is assigned while callers '
        'wait. Admission failures happen before SQL dispatch, so the primary '
        'database can remain healthy while callers cannot obtain a session.'
    ),
    (
        'RUN-008',
        'Tax connector route profiles and certificate inventory',
        'payment-service',
        'Tax connector profile 41 targets api.tax-partner.example and sends '
        'api.tax-partner.example as SNI. Profile 42 targets tax-gateway.internal '
        'and sends tax-gateway.internal as SNI. Both profiles reference trusted '
        'certificate bundle TAX-2026, which remains valid through December 2026. '
        'The bundle DNS identities contain api.tax-partner.example but do not '
        'contain tax-gateway.internal. Connector profiles do not modify the trust '
        'store.'
    ),
    (
        'RUN-009',
        'Notification delivery lifecycle and probe coverage',
        'notification-service',
        'Notification state S1 means ready for a delivery worker. After a worker '
        'dequeues a notification and the provider returns 202 Accepted, it enters '
        'S4. Only the provider delivery-receipt callback moves an item out of S4; '
        'delivery workers no longer own items in that state. Worker throughput '
        'measures dequeue and submission, not delivery-receipt completion. The '
        'provider gateway health check tests message admission only and does not '
        'test post-acceptance delivery or receipt callbacks.'
    ),
    (
        'RUN-010',
        'Invoice signing receipt callbacks and completion states',
        'invoice-service',
        'Invoice uploads accepted by a signing provider are not complete until a '
        'signed receipt callback arrives. Check receipt age, callback delivery '
        'status and endpoint errors alongside successful upload responses. '
        'Healthy uploads do not demonstrate callback availability. Confirm '
        'provider callback recovery before replaying receipt events; deduplicate '
        'replayed events by receipt ID.'
    ),
    (
        'RUN-011',
        'Checkout lock waits after a migration',
        'checkout-service',
        'When checkout requests block during a database migration, inspect lock '
        'wait chains and the transaction holding the contested table or row '
        'locks. Compare migration start time with the first wait and inspect '
        'whether the migration transaction remains open. Pool exhaustion can be a'
        ' downstream symptom of blocked transactions. Obtain approval before '
        'canceling a migration or terminating its transaction.'
    ),
    (
        'RUN-012',
        'DNS resolution failures and stale service records',
        'platform-service',
        'For connection failures before any TCP handshake, inspect resolver '
        'errors, DNS response codes, record TTLs and the resolved address from '
        'the affected workload. Compare with the intended service endpoint and a '
        'working resolver. A healthy destination does not exclude a DNS failure. '
        'Correct the authoritative record or resolver configuration through the '
        'approved change process, then verify resolution from affected workloads.'
    ),
    (
        'RUN-013',
        'API rate limits and retry amplification',
        'api-gateway',
        'For HTTP 429 responses, inspect the rate-limit scope, Retry-After '
        'headers, request volume and retry frequency. Separate upstream '
        'throttling from local worker saturation using response codes and queue '
        'timings. Apply bounded exponential backoff with jitter and honor Retry-'
        'After. Coordinate quota changes with the service owner; do not retry all'
        ' queued requests simultaneously.'
    ),
    (
        'RUN-014',
        'Disk exhaustion and failed application writes',
        'storage-service',
        'For failed writes, inspect filesystem free bytes, free inodes, mount '
        'state and the exact write error. ENOSPC can indicate exhausted blocks or'
        ' inodes; a read-only mount is a different failure. Correlate application'
        ' errors with the affected volume. Follow retention policy before '
        'removing data and obtain approval for capacity changes. Confirm '
        'successful writes after remediation.'
    ),
    (
        'RUN-015',
        'Deployment memory limits and container restarts',
        'platform-service',
        'For repeated container restarts, inspect termination reason, exit '
        'status, memory usage, configured memory limit and deployment changes. '
        'OOMKilled with memory at the limit supports memory exhaustion; a restart'
        ' count alone does not. Distinguish a lower limit from increasing '
        'application memory usage. Roll back an incorrect limit through the '
        'approved process and investigate leaks before increasing capacity '
        'indefinitely.'
    )
ON CONFLICT (id) DO UPDATE
SET
    embedding = CASE
        WHEN runbooks.title IS DISTINCT FROM EXCLUDED.title
            OR runbooks.content IS DISTINCT FROM EXCLUDED.content
        THEN NULL
        ELSE runbooks.embedding
    END,
    title = EXCLUDED.title,
    service = EXCLUDED.service,
    content = EXCLUDED.content;
