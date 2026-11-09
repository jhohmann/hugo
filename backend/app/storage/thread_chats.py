"""Explicit message references and read-only conversation views for a thread."""

from app.storage.database import get_connection


def link_message(message_id: int, thread_ids: list[int]) -> None:
    if not thread_ids:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO thread_messages (thread_id, message_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                [(tid, message_id) for tid in thread_ids],
            )


def link_answer(source_message_id: int, answer_id: int) -> None:
    # Includes references created by the model's thread create/update tools.
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO thread_messages (thread_id, message_id)
               SELECT tm.thread_id, a.id FROM thread_messages tm
               JOIN messages u ON u.id = tm.message_id
               JOIN messages a ON a.id = %s AND a.conversation_id = u.conversation_id
               WHERE tm.message_id = %s AND a.role = 'assistant'
               ON CONFLICT DO NOTHING""", (answer_id, source_message_id),
        )


def conversation_threads(conversation_ids: list[int]) -> dict[int, list[dict]]:
    if not conversation_ids:
        return {}
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT m.conversation_id, t.id, t.title FROM messages m
               JOIN thread_messages tm ON tm.message_id = m.id
               JOIN threads t ON t.id = tm.thread_id
               WHERE m.conversation_id = ANY(%s) ORDER BY m.conversation_id, t.id""",
            (conversation_ids,),
        ).fetchall()
    result = {}
    for cid, tid, title in rows:
        result.setdefault(cid, []).append({"id": tid, "title": title})
    return result


def thread_conversations(thread_id: int, page: int = 1) -> dict:
    """Five conversations per page, with their latest twelve complete messages."""
    page = max(1, page)
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT m.conversation_id, MAX(m.created_at) AS last_linked,
                      (SELECT content FROM messages first_message
                       WHERE first_message.conversation_id = m.conversation_id
                       AND first_message.role = 'user' ORDER BY id LIMIT 1)
               FROM thread_messages tm JOIN messages m ON m.id = tm.message_id
               WHERE tm.thread_id = %s
               GROUP BY m.conversation_id
               ORDER BY last_linked DESC, m.conversation_id DESC LIMIT 6 OFFSET %s""",
            (thread_id, (page - 1) * 5),
        ).fetchall()
        items = []
        for cid, last_linked, preview in rows[:5]:
            messages = conn.execute(
                """SELECT role, content, created_at FROM messages
                   WHERE conversation_id = %s AND role IN ('user', 'assistant')
                   ORDER BY id DESC LIMIT 13""", (cid,),
            ).fetchall()
            items.append({"id": cid, "preview": preview, "last_linked": last_linked,
                          "has_older": len(messages) > 12,
                          "messages": [dict(zip(("role", "content", "created_at"), m))
                                       for m in reversed(messages[:12])]})
    return {"items": items, "has_more": len(rows) > 5, "page": page}
