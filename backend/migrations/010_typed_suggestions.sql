-- Preserve existing suggestions as proposals; replies are immutable user evidence.
ALTER TABLE suggestions
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'proposal'
        CHECK (kind IN ('proposal', 'status_check', 'question')),
    ADD COLUMN response_options JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(response_options) = 'array'),
    ADD COLUMN allow_free_text BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN revision BIGINT NOT NULL DEFAULT 1 CHECK (revision > 0);
ALTER TABLE suggestions ADD CONSTRAINT suggestions_response_contract_check CHECK (
    (kind = 'question' AND (allow_free_text OR jsonb_array_length(response_options) > 0))
    OR (kind <> 'question' AND NOT allow_free_text AND response_options = '[]'::jsonb)
);

CREATE TABLE suggestion_responses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    suggestion_id BIGINT NOT NULL UNIQUE REFERENCES suggestions(id) ON DELETE CASCADE,
    answer TEXT NOT NULL,
    response_text TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('ui', 'api')),
    message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
