CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS embedding vector(384);

CREATE INDEX IF NOT EXISTS idx_memories_embedding
ON memories
USING hnsw (embedding vector_cosine_ops);
