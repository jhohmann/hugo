-- History starts here; existing state is not a reconstructed change history.
CREATE TABLE thread_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id BIGINT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    kind TEXT NOT NULL CHECK (kind IN ('created', 'updated')),
    origin TEXT NOT NULL CHECK (origin IN ('conversation', 'internal')),
    source_message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    changes JSONB NOT NULL CHECK (jsonb_typeof(changes) = 'object' AND changes <> '{}'::jsonb),
    automatic_fields TEXT[] NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_thread_events_history ON thread_events(thread_id, recorded_at, id);
CREATE INDEX idx_thread_events_sequence ON thread_events(thread_id, id);
