-- Hugo: Semantische Suche für Handlungsstränge (Threads)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE threads
ADD COLUMN IF NOT EXISTS embedding vector(384);

CREATE INDEX IF NOT EXISTS idx_threads_embedding
ON threads
USING hnsw (embedding vector_cosine_ops);
