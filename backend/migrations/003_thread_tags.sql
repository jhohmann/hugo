-- Migration 003: Tags für Threads (Arbeit/Privat)
-- Ermöglicht die spätere Trennung von Arbeits- und Privatthemen.

CREATE TABLE IF NOT EXISTS thread_tags (
    thread_id BIGINT NOT NULL
        REFERENCES threads(id) ON DELETE CASCADE,
    tag TEXT NOT NULL
        CHECK (tag IN ('arbeit', 'privat')),
    PRIMARY KEY (thread_id, tag)
);

-- Index für schnelle Filterung nach Tag
CREATE INDEX IF NOT EXISTS idx_thread_tags_tag
    ON thread_tags(tag);

-- Kommentar für Dokumentation
COMMENT ON TABLE thread_tags IS
    'Tags für Threads: arbeit, privat. Ermöglicht spätere Arbeits-/Privattrennung.';
