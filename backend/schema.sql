
-- Hugo: Initiales Datenbankschema

CREATE TABLE conversations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id BIGINT NOT NULL
        REFERENCES conversations(id),
    role TEXT NOT NULL
        CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation
    ON messages(conversation_id, id);

CREATE TABLE memories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
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

CREATE TABLE threads (
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Verknüpfung von Wissen und Handlungssträngen

CREATE TABLE thread_memories (
    thread_id BIGINT NOT NULL
        REFERENCES threads(id) ON DELETE CASCADE,
    memory_id BIGINT NOT NULL
        REFERENCES memories(id) ON DELETE CASCADE,
    PRIMARY KEY (thread_id, memory_id)
);

-- Nachvollziehbarkeit: Welche Nachrichten
-- gehören zu welchem Handlungsstrang?

CREATE TABLE thread_messages (
    thread_id BIGINT NOT NULL
        REFERENCES threads(id) ON DELETE CASCADE,
    message_id BIGINT NOT NULL
        REFERENCES messages(id) ON DELETE CASCADE,
    PRIMARY KEY (thread_id, message_id)
);
