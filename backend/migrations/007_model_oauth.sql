-- Single-user OAuth registration, shared by web and worker.
-- Credentials are secrets, just like google_credentials; protect DB backups.
CREATE TABLE model_oauth (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    host_id TEXT NOT NULL,
    registration JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
