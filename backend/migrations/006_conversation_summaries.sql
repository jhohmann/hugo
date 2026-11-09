-- Derived context only; original messages remain the authoritative transcript.
CREATE TABLE conversation_summaries (
    conversation_id BIGINT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    through_message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
