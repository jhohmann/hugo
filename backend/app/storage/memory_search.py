
from pgvector.psycopg import register_vector

from app.storage.database import get_connection
from app.storage.embeddings import (
    embed_document,
    embed_query,
)


def add_memory(content: str) -> int:
    embedding = embed_document(content)

    with get_connection() as conn:
        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memories (content, embedding)
                VALUES (%s, %s)
                RETURNING id
                """,
                (content, embedding)
            )
            return cur.fetchone()[0]


def search_memories(query: str, limit: int = 5):
    embedding = embed_query(query)

    with get_connection() as conn:
        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    content,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM memories
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding, embedding, limit)
            )

            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "similarity": round(float(row[2]), 3)
                }
                for row in cur.fetchall()
            ]


def create_memory(content: str, source_message_id: int):
    
    existing_id = find_exact_memory(content)
    if existing_id is not None:
        return existing_id

    embedding = embed_document(content)

    with get_connection() as conn:
        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memories
                    (content, embedding, source_message_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (content, embedding, source_message_id)
            )
            return cur.fetchone()[0]


def update_memory(memory_id: int, content: str):
    embedding = embed_document(content)

    with get_connection() as conn:
        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE memories
                SET content = %s,
                    embedding = %s,
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'proposed'
                RETURNING id
                """,
                (content, embedding, memory_id)
            )
            return cur.fetchone()


def find_exact_memory(content: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM memories
                WHERE lower(trim(content)) = lower(trim(%s))
                  AND status != 'outdated'
                LIMIT 1
                """,
                (content,)
            )
            row = cur.fetchone()
            return row[0] if row else None

def list_memories(limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content, category, status,
                       created_at, updated_at
                FROM memories
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )

            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                }
                for row in cur.fetchall()
            ]