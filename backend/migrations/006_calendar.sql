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
