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
