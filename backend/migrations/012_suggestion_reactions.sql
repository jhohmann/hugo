-- A stable model-selected occasion identity survives rewording and evaluation runs.
ALTER TABLE suggestions ADD COLUMN occasion_key TEXT;
CREATE UNIQUE INDEX idx_suggestions_occasion
    ON suggestions (thread_id, occasion_key) NULLS NOT DISTINCT
    WHERE occasion_key IS NOT NULL;

CREATE TABLE suggestion_reactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    suggestion_id BIGINT NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('confirmed', 'deferred', 'dismissed')),
    deferred_until DATE,
    source TEXT NOT NULL CHECK (source IN ('ui', 'api', 'chat', 'internal')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX idx_suggestion_reactions_recent ON suggestion_reactions (created_at DESC, id DESC);
