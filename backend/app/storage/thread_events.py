"""Thread change history; writes always use the caller's transaction."""

from datetime import date, datetime, timezone

from psycopg.types.json import Jsonb

from app.storage.database import get_connection


TRACKED_FIELDS = (
    "title", "description", "status", "priority", "deadline", "event_start",
    "event_end", "time_precision", "act_by", "time_text", "next_action",
    "blocked_reason", "preparation_weeks", "tags", "review_on", "waiting_for",
)


def _json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def record_thread_event(cur, before, after, *, source_message_id=None, automatic_fields=()):
    """Record actual persisted differences, excluding technical fields."""
    changes = {}
    for field in TRACKED_FIELDS:
        old = before[field] if before is not None else None
        new = after[field]
        if old != new:
            changes[field] = {"before": _json_value(old), "after": _json_value(new)}
    if not changes:
        return
    cur.execute(
        """INSERT INTO thread_events
           (thread_id, kind, origin, source_message_id, changes, automatic_fields)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            after["id"], "created" if before is None else "updated",
            "conversation" if source_message_id is not None else "internal",
            source_message_id, Jsonb(changes), sorted(set(automatic_fields) & changes.keys()),
        ),
    )


def _parse_boundary(value):
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("Zeitraumgrenzen müssen ISO-Zeitstempel mit Zeitzone sein.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Zeitraumgrenzen benötigen eine Zeitzone.")
    return parsed.astimezone(timezone.utc)


def list_thread_events(thread_id: int, *, after_id: int = 0, limit: int = 50) -> list[dict]:
    """Compatibility view of a page in recording sequence."""
    return list_thread_events_page(thread_id, after_id=after_id, limit=limit)["events"]


def list_thread_events_page(
    thread_id: int, *, after_id: int = 0, limit: int = 50,
    since=None, until=None,
) -> dict:
    """Read recorded events in ID order; since inclusive, until exclusive."""
    if type(thread_id) is not int or thread_id < 1:
        raise ValueError("thread_id muss eine positive Ganzzahl sein.")
    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id muss eine nichtnegative Ganzzahl sein.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit muss zwischen 1 und 100 liegen.")
    since, until = _parse_boundary(since), _parse_boundary(until)
    if since is not None and until is not None and since >= until:
        raise ValueError("since muss vor until liegen.")
    conditions = ["thread_id = %s", "id > %s"]
    params = [thread_id, after_id]
    for boundary, operator in ((since, ">="), (until, "<")):
        if boundary is not None:
            conditions.append(f"recorded_at {operator} %s")
            params.append(boundary)
    params.append(limit + 1)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM threads WHERE id = %s", (thread_id,))
            found = cur.fetchone() is not None
            cur.execute(
                f"""SELECT id, thread_id, recorded_at, kind, origin,
                          source_message_id, changes, automatic_fields
                   FROM thread_events WHERE {' AND '.join(conditions)}
                   ORDER BY id LIMIT %s""",
                params,
            )
            keys = ("id", "thread_id", "recorded_at", "kind", "origin",
                    "source_message_id", "changes", "automatic_fields")
            rows = cur.fetchall()
            events = [dict(zip(keys, row)) for row in rows[:limit]]
            has_more = len(rows) > limit
            return {
                "thread_id": thread_id, "found": found, "events": events,
                "has_more": has_more,
                "next_after_id": events[-1]["id"] if has_more else None,
                "history_note": "Erfasst Änderungen seit Einführung des Protokolls; fehlende Ereignisse beweisen keine Untätigkeit.",
            }
