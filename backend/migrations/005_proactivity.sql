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
