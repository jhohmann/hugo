
import os
import psycopg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://hugo:hugo_dev@localhost:5432/hugo"
)


def get_connection():
    return psycopg.connect(DATABASE_URL)


def create_conversation(title=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (title)
                VALUES (%s)
                RETURNING id
                """,
                (title,)
            )
            return cur.fetchone()[0]


def save_message(conversation_id, role, content):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (conversation_id, role, content)
            )
            return cur.fetchone()[0]


def list_conversations(limit=50):
    """Jüngste Unterhaltungen mit Vorschau, zuletzt aktiv zuerst."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id,
                       c.created_at,
                       COUNT(m.id) AS message_count,
                       MAX(m.created_at) AS last_activity,
                       (
                           SELECT m2.content
                           FROM messages m2
                           WHERE m2.conversation_id = c.id
                             AND m2.role = 'user'
                           ORDER BY m2.id
                           LIMIT 1
                       ) AS preview
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                GROUP BY c.id
                ORDER BY MAX(m.created_at) DESC NULLS LAST,
                         c.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {
                    "id": row[0],
                    "created_at": row[1],
                    "message_count": row[2],
                    "last_activity": row[3],
                    "preview": row[4],
                }
                for row in cur.fetchall()
            ]


def get_messages(conversation_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
                FROM messages
                WHERE conversation_id = %s
                ORDER BY id
                """,
                (conversation_id,)
            )
            return [
                {"role": role, "content": content}
                for role, content in cur.fetchall()
            ]
