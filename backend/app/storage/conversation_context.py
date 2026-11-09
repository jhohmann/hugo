"""Persistent, replaceable summaries; never rewrite the original conversation."""

from app.storage.database import get_connection


def load_context(conversation_id: int, through_id: int) -> tuple[dict | None, list[dict]]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT through_message_id, content FROM conversation_summaries
               WHERE conversation_id = %s AND through_message_id < %s""",
            (conversation_id, through_id),
        ).fetchone()
        summary = {"through_message_id": row[0], "content": row[1]} if row else None
        rows = conn.execute(
            """SELECT id, role, content, created_at FROM messages
               WHERE conversation_id = %s AND id > %s AND id <= %s ORDER BY id""",
            (conversation_id, row[0] if row else 0, through_id),
        ).fetchall()
    return summary, [dict(zip(("id", "role", "content", "created_at"), row)) for row in rows]


def save_summary(conversation_id: int, through_id: int, content: str, expected_id: int) -> bool:
    """Compare-and-swap prevents concurrent requests overwriting newer context."""
    if not content.strip() or through_id <= expected_id:
        raise ValueError("Ungültiger Zusammenfassungsfortschritt.")
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO conversation_summaries (conversation_id, through_message_id, content)
               SELECT conversation_id, id, %s FROM messages
               WHERE conversation_id = %s AND id = %s
               ON CONFLICT (conversation_id) DO UPDATE
               SET through_message_id = EXCLUDED.through_message_id,
                   content = EXCLUDED.content, updated_at = NOW()
               WHERE conversation_summaries.through_message_id = %s
               RETURNING through_message_id""",
            (content, conversation_id, through_id, expected_id),
        ).fetchone()
    return row is not None
