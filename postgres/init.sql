-- =============================================================================
-- AI Stack — database initialization (run once by the postgres container)
-- pgvector/pgvector:pg16 already ships the vector extension.
-- =============================================================================

-- Applications create their own schemas; we only ensure DBs + extensions exist.
-- Open WebUI: schema + pgvector managed by the app on first boot.
-- LiteLLM: creates its own tables on first boot (budget/spend state).
-- Orchestrator: schema defined below.

-- Databases are created via POSTGRES_MULTIPLE_DATABASES-style bootstrap below
-- is not supported by the official image; instead we create them here against
-- the single POSTGRES_DB, guarded with DO blocks.

\set ON_ERROR_STOP on

-- pgvector (available in pgvector/pgvector:pg16 image)
CREATE EXTENSION IF NOT EXISTS vector;

-- -----------------------------------------------------------------------------
-- orchestrator schema
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS orchestrator;

-- Coding approval workflow (Milestone 3)
CREATE TABLE IF NOT EXISTS orchestrator.approvals (
    id            BIGSERIAL PRIMARY KEY,
    thread_id     TEXT        NOT NULL,
    agent_id      TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','approved','rejected','cancelled')),
    request       TEXT        NOT NULL,
    plan          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    allowed_files JSONB       NOT NULL DEFAULT '[]'::jsonb,
    proposed_diff JSONB       NOT NULL DEFAULT '{}'::jsonb,
    result_diff   JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS approvals_thread_idx     ON orchestrator.approvals (thread_id);
CREATE INDEX IF NOT EXISTS approvals_status_idx     ON orchestrator.approvals (status);
CREATE INDEX IF NOT EXISTS approvals_agent_idx      ON orchestrator.approvals (agent_id);

-- LangGraph checkpoint persistence (state serialized as JSONB)
CREATE TABLE IF NOT EXISTS orchestrator.checkpoints (
    id            BIGSERIAL   PRIMARY KEY,
    thread_id     TEXT        NOT NULL,
    checkpoint_id TEXT        NOT NULL,
    parent_id     TEXT,
    state         JSONB       NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (thread_id, checkpoint_id)
);
CREATE INDEX IF NOT EXISTS checkpoints_thread_idx ON orchestrator.checkpoints (thread_id, created_at DESC);

-- Browser security gateway audit log (Milestone 2)
CREATE TABLE IF NOT EXISTS orchestrator.browser_audit (
    id         BIGSERIAL   PRIMARY KEY,
    agent_id   TEXT        NOT NULL,
    url        TEXT        NOT NULL,
    tool       TEXT        NOT NULL,
    tier       TEXT,
    status     TEXT        NOT NULL,
    detail     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS browser_audit_agent_idx ON orchestrator.browser_audit (agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS browser_audit_url_idx  ON orchestrator.browser_audit (url);

-- Research persistence (Milestone 3)
CREATE TABLE IF NOT EXISTS orchestrator.research_notes (
    id              BIGSERIAL   PRIMARY KEY,
    agent_id        TEXT        NOT NULL,
    query           TEXT        NOT NULL,
    source_urls     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    summary         TEXT,
    comparison_data JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS research_notes_query_idx ON orchestrator.research_notes (query);
CREATE INDEX IF NOT EXISTS research_notes_agent_idx ON orchestrator.research_notes (agent_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- LiteLLM database (app creates its own tables)
-- -----------------------------------------------------------------------------
CREATE DATABASE litellm;
GRANT ALL PRIVILEGES ON DATABASE litellm TO postgres;

-- -----------------------------------------------------------------------------
-- Open WebUI database (app creates its own tables + pgvector)
-- -----------------------------------------------------------------------------
CREATE DATABASE openwebui;
GRANT ALL PRIVILEGES ON DATABASE openwebui TO postgres;

\connect openwebui
CREATE EXTENSION IF NOT EXISTS vector;
