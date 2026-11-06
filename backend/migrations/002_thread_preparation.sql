-- Migration 002: Vorbereitungsfenster und Blocker-Erkennung für Threads
-- Fügt blocked_reason und preparation_weeks hinzu, ohne bestehende Daten zu ändern.

ALTER TABLE threads
    ADD COLUMN IF NOT EXISTS blocked_reason TEXT,
    ADD COLUMN IF NOT EXISTS preparation_weeks INTEGER;

-- Index für schnelle Suche nach blockierten Threads
CREATE INDEX IF NOT EXISTS idx_threads_blocked
    ON threads(status, blocked_reason)
    WHERE blocked_reason IS NOT NULL;

-- Kommentare für Dokumentation
COMMENT ON COLUMN threads.blocked_reason IS
    'Warum das Vorhaben wartet (z. B. "Visum noch nicht beantragt", "Warte auf Rückmeldung")';
COMMENT ON COLUMN threads.preparation_weeks IS
    'Wie viele Wochen vor event_start oder act_by sollte begonnen werden';
