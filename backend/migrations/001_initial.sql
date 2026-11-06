
-- Hugo: consolidated pre-deployment baseline (2026-11-06).
-- Immutable after adoption; future changes belong in 002_*.sql and later.
-- IF NOT EXISTS adopts the complete local development schema without deleting data.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id BIGINT NOT NULL
        REFERENCES conversations(id),
    role TEXT NOT NULL
        CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS memories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    embedding vector(384),
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN (
            'proposed', 'confirmed', 'outdated'
        )),
    valid_from TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    source_message_id BIGINT
        REFERENCES messages(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS threads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN (
            'proposed', 'active', 'waiting',
            'completed', 'archived'
        )),
    priority SMALLINT,
    deadline TIMESTAMPTZ,
    next_action TEXT,
    embedding vector(384),
    event_start DATE,
    event_end DATE,
    time_precision TEXT NOT NULL DEFAULT 'exact'
        CHECK (time_precision IN ('exact', 'approximate')),
    act_by DATE,
    time_text TEXT,
    CONSTRAINT threads_event_range_check CHECK (
        event_end IS NULL OR (event_start IS NOT NULL AND event_end >= event_start)
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Verknüpfung von Wissen und Handlungssträngen

CREATE TABLE IF NOT EXISTS thread_memories (
    thread_id BIGINT NOT NULL
        REFERENCES threads(id) ON DELETE CASCADE,
    memory_id BIGINT NOT NULL
        REFERENCES memories(id) ON DELETE CASCADE,
    PRIMARY KEY (thread_id, memory_id)
);

-- Nachvollziehbarkeit: Welche Nachrichten
-- gehören zu welchem Handlungsstrang?

CREATE TABLE IF NOT EXISTS thread_messages (
    thread_id BIGINT NOT NULL
        REFERENCES threads(id) ON DELETE CASCADE,
    message_id BIGINT NOT NULL
        REFERENCES messages(id) ON DELETE CASCADE,
    PRIMARY KEY (thread_id, message_id)
);


CREATE INDEX IF NOT EXISTS idx_memories_embedding
    ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_threads_embedding
    ON threads USING hnsw (embedding vector_cosine_ops);

-- Hugo: Proaktivitäts-Engine — Evaluationsläufe und Vorschläge
--
-- evaluation_runs: Nachvollziehbarkeit jedes Bewertungslaufs
--   (manuell jetzt, geplant später).
-- suggestions: proaktive Vorschläge mit Begründung, Priorität,
--   Zustellstatus (delivery_status) und Bearbeitungsstatus (status).

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trigger_source TEXT NOT NULL DEFAULT 'manual'
        CHECK (trigger_source IN ('manual', 'scheduled')),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    threads_considered INTEGER,
    suggestions_created INTEGER,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS suggestions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id BIGINT
        REFERENCES threads(id) ON DELETE SET NULL,
    run_id BIGINT
        REFERENCES evaluation_runs(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    reason TEXT,
    priority SMALLINT
        CHECK (priority BETWEEN 1 AND 5),
    suggested_date DATE,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'surfaced')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN (
            'open', 'confirmed', 'deferred', 'dismissed'
        )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_suggestions_thread
    ON suggestions(thread_id);

CREATE INDEX IF NOT EXISTS idx_suggestions_status
    ON suggestions(status, delivery_status);

-- Hugo: Google-Calendar-Integration
--
-- google_credentials: OAuth-Tokens des einen verbundenen
--   Google-Kontos (Single-User). Nicht im Repository, nur in
--   der Datenbank.
-- google_oauth_states: CSRF-Schutz für den OAuth-Flow
--   (neustartfest statt im Speicher).
-- calendar_actions: ausstehende, bestätigungspflichtige
--   Schreibaktionen. Der Agent erzeugt hier nur Vorschläge;
--   die Ausführung erfolgt ausschließlich nach expliziter
--   Bestätigung über die Weboberfläche.
-- calendar_action_log: internes Aktionsprotokoll, insbesondere
--   für Löschungen (die Terminbeschreibung ist nach dem
--   Löschen nicht mehr verfügbar).

CREATE TABLE IF NOT EXISTS google_credentials (
    id SMALLINT PRIMARY KEY DEFAULT 1
        CHECK (id = 1),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    scopes TEXT NOT NULL,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS google_oauth_states (
    state TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS calendar_actions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_type TEXT NOT NULL
        CHECK (action_type IN ('create', 'update', 'delete')),
    calendar_id TEXT NOT NULL,
    event_id TEXT,
    -- Vorgeschlagene Felder: summary, description, location,
    -- start, end, all_day
    payload JSONB NOT NULL,
    -- Terminzustand zum Zeitpunkt des Vorschlags
    -- (etag, updated, summary, start, end, ...) für die
    -- Konflikterkennung bei update/delete.
    snapshot JSONB,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',   -- wartet auf Bestätigung
            'confirmed', -- bestätigt, Ausführung läuft
            'rejected',  -- vom Nutzer abgelehnt
            'executed',  -- erfolgreich ausgeführt
            'failed',    -- Ausführung fehlgeschlagen
            'conflict'   -- Termin wurde seit dem Vorschlag
                         -- verändert; erneute Bestätigung nötig
        )),
    result JSONB,
    error TEXT,
    source_message_id BIGINT
        REFERENCES messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_calendar_actions_status
    ON calendar_actions(status);

CREATE TABLE IF NOT EXISTS calendar_action_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_id BIGINT
        REFERENCES calendar_actions(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    calendar_id TEXT NOT NULL,
    event_id TEXT,
    summary TEXT,
    detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_action_log_action
    ON calendar_action_log(action_id);

-- Single-user authentication; raw session tokens never enter the database.
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    password_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);

-- Shared login throttle, including across web workers/restarts.
CREATE TABLE IF NOT EXISTS auth_login_limit (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    window_start TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL
);

-- Fail rather than silently adopting a partial, obsolete development schema.
-- These columns were added after the original unversioned schema.
SELECT embedding FROM memories LIMIT 0;
SELECT embedding, event_start, event_end, time_precision, act_by, time_text
    FROM threads LIMIT 0;
