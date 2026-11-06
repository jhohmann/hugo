from datetime import datetime, timezone

from pgvector.psycopg import register_vector

from app.storage.database import get_connection
from app.storage.thread_events import record_thread_event
from app.storage.embeddings import (
    embed_document,
    embed_query,
)
from app.tools.dates import parse_date, today_berlin

# Statusmodell:
# proposed  = unverbindliche Überlegung oder Option
# active    = konkret beschlossenes Vorhaben
# waiting   = wartet auf etwas oder jemanden
# completed = abgeschlossen
# archived  = verworfen oder nicht mehr relevant
THREAD_STATUSES = (
    "proposed",
    "active",
    "waiting",
    "completed",
    "archived",
)

CLOSED_STATUSES = ("completed", "archived")
THREAD_TAGS = ("arbeit", "privat")

MIN_PRIORITY = 1
MAX_PRIORITY = 5

COLUMNS = (
    "id, title, description, status, priority,"
    " deadline, event_start, event_end, time_precision,"
    " act_by, time_text, next_action, blocked_reason,"
    " preparation_weeks, created_at, updated_at,"
    " ARRAY(SELECT tag FROM thread_tags"
    " WHERE thread_id = threads.id ORDER BY tag) AS tags,"
    " review_on, waiting_for"
)

# Genauigkeit der Zeitangabe:
# exact       = exakter Termin oder genau bekannter Zeitraum
# approximate = ungefähre Angabe (z. B. 'Mitte Juni');
#               die Originalangabe steht in time_text
TIME_PRECISIONS = ("exact", "approximate")


def validate_tag(tag):
    if tag is not None and tag not in THREAD_TAGS:
        raise ValueError("Ungültiger Bereich. Erlaubt: Arbeit, Privat.")
    return tag


def _validate_tags(tags):
    if tags is None:
        return None
    if not isinstance(tags, list):
        raise ValueError("tags muss eine Liste sein.")
    for tag in tags:
        if not isinstance(tag, str):
            raise ValueError("Jeder Tag muss eine Zeichenkette sein.")
        validate_tag(tag)
    return sorted(set(tags))


def _set_tags(cur, thread_id, tags):
    cur.execute("DELETE FROM thread_tags WHERE thread_id = %s", (thread_id,))
    cur.executemany(
        "INSERT INTO thread_tags (thread_id, tag) VALUES (%s, %s)",
        [(thread_id, tag) for tag in tags],
    )


def _validate_status(status):
    if status is None:
        return None
    if status not in THREAD_STATUSES:
        raise ValueError(
            f"Ungültiger Thread-Status: {status!r}."
            f" Erlaubt: {', '.join(THREAD_STATUSES)}"
        )
    return status


def _validate_priority(priority):
    if priority is None:
        return None
    priority = int(priority)
    if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
        raise ValueError(
            f"Ungültige Priorität: {priority}."
            f" Erlaubt: {MIN_PRIORITY} bis {MAX_PRIORITY}"
        )
    return priority


def _validate_time_precision(precision):
    if precision is None:
        return None
    if precision not in TIME_PRECISIONS:
        raise ValueError(
            f"Ungültige Zeit-Genauigkeit: {precision!r}."
            f" Erlaubt: {', '.join(TIME_PRECISIONS)}"
        )
    return precision


def _validate_event_range(event_start, event_end):
    if event_end is not None and event_start is None:
        raise ValueError(
            "event_end ohne event_start ist nicht möglich."
        )
    if (
        event_start is not None
        and event_end is not None
        and event_end < event_start
    ):
        raise ValueError(
            "event_end liegt vor event_start."
        )


def _parse_deadline(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        raise ValueError(
            f"Ungültiges Datumsformat: {value!r}."
            " ISO 8601 erwartet, z. B. '2026-06-15'."
        )
    if parsed.tzinfo is None:
        # Ohne Zeitzone wird UTC angenommen.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _embed_thread(title: str, description: str | None):
    text = title if not description else f"{title}\n{description}"
    return embed_document(text)


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "status": row[3],
        "priority": row[4],
        "deadline": row[5],
        "event_start": row[6],
        "event_end": row[7],
        "time_precision": row[8],
        "act_by": row[9],
        "time_text": row[10],
        "next_action": row[11],
        "blocked_reason": row[12],
        "preparation_weeks": row[13],
        "created_at": row[14],
        "updated_at": row[15],
        "tags": row[16],
        "review_on": row[17],
        "waiting_for": row[18],
    }


def _link_message(cur, thread_id: int, message_id: int | None):
    if message_id is None:
        return
    cur.execute(
        """
        INSERT INTO thread_messages (thread_id, message_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        (thread_id, message_id),
    )


def create_thread(
    title: str,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    deadline=None,
    event_start=None,
    event_end=None,
    time_precision: str | None = None,
    act_by=None,
    time_text: str | None = None,
    next_action: str | None = None,
    blocked_reason: str | None = None,
    preparation_weeks: int | None = None,
    source_message_id: int | None = None,
    tags: list[str] | None = None,
    review_on=None,
    waiting_for: str | None = None,
) -> int:
    review_on = parse_date(review_on)
    tags = _validate_tags(tags)
    status = _validate_status(status) or "proposed"
    if status in CLOSED_STATUSES:
        review_on = waiting_for = blocked_reason = None
    priority = _validate_priority(priority)
    deadline = _parse_deadline(deadline)
    event_start = parse_date(event_start)
    event_end = parse_date(event_end)
    _validate_event_range(event_start, event_end)
    time_precision = (
        _validate_time_precision(time_precision) or "exact"
    )
    act_by = parse_date(act_by)
    embedding = _embed_thread(title, description)

    with get_connection() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO threads
                    (title, description, status, priority,
                     deadline, event_start, event_end,
                     time_precision, act_by, time_text,
                     next_action, blocked_reason,
                     preparation_weeks, embedding, review_on, waiting_for)
                VALUES (%s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    title, description, status, priority,
                    deadline, event_start, event_end,
                    time_precision, act_by, time_text,
                    next_action, blocked_reason,
                    preparation_weeks, embedding, review_on, waiting_for,
                ),
            )
            thread_id = cur.fetchone()[0]
            if tags:
                _set_tags(cur, thread_id, tags)
            _link_message(cur, thread_id, source_message_id)
            cur.execute(f"SELECT {COLUMNS} FROM threads WHERE id = %s", (thread_id,))
            record_thread_event(cur, None, _row_to_dict(cur.fetchone()), source_message_id=source_message_id)
            return thread_id


def get_thread(thread_id: int) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {COLUMNS} FROM threads WHERE id = %s",
                (thread_id,),
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None


def list_threads(
    status: str | None = None,
    limit: int = 50,
    open_only: bool = False,
    tag: str | None = None,
    review_due_only: bool = False,
) -> list[dict]:
    status = _validate_status(status)
    tag = validate_tag(tag)

    where = ""
    params: list = []
    if open_only:
        where = "WHERE status NOT IN ('completed', 'archived')"
    elif status is not None:
        where = "WHERE status = %s"
        params.append(status)
    if tag is not None:
        where += " AND " if where else "WHERE "
        where += "EXISTS (SELECT 1 FROM thread_tags WHERE thread_id = threads.id AND tag = %s)"
        params.append(tag)
    if review_due_only:
        where += " AND " if where else "WHERE "
        where += """status NOT IN ('completed', 'archived')
            AND (review_on IS NULL OR review_on <= %s)
            AND NOT EXISTS (
                SELECT 1 FROM suggestions s WHERE s.thread_id = threads.id
                AND s.status = 'deferred'
                AND (s.deferred_until IS NULL OR s.deferred_until > %s)
            )"""
        params.extend([today_berlin(), today_berlin()])
    params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {COLUMNS}
                FROM threads
                {where}
                ORDER BY
                    CASE
                        WHEN status IN ('completed', 'archived')
                        THEN 1 ELSE 0
                    END,
                    LEAST(review_on, act_by, event_start, deadline::date)
                        ASC NULLS LAST,
                    priority DESC NULLS LAST,
                    id
                LIMIT %s
                """,
                params,
            )
            return [_row_to_dict(row) for row in cur.fetchall()]


def search_threads(
    query: str,
    status: str | None = None,
    limit: int = 10,
    tag: str | None = None,
) -> list[dict]:
    status = _validate_status(status)
    tag = validate_tag(tag)
    embedding = embed_query(query)

    # Platzhalter: Similarity, optionale Filter, Sortiervektor, Limit.
    where = "embedding IS NOT NULL"
    params: list = [embedding]
    if status is not None:
        where += " AND status = %s"
        params.append(status)
    if tag is not None:
        where += " AND EXISTS (SELECT 1 FROM thread_tags WHERE thread_id = threads.id AND tag = %s)"
        params.append(tag)
    params.extend([embedding, limit])

    with get_connection() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    {COLUMNS},
                    1 - (embedding <=> %s::vector) AS similarity
                FROM threads
                WHERE {where}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                params,
            )
            results = []
            for row in cur.fetchall():
                thread = _row_to_dict(row[:-1])
                thread["similarity"] = round(float(row[-1]), 3)
                results.append(thread)
            return results


def update_thread(
    thread_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    deadline=None,
    event_start=None,
    event_end=None,
    time_precision: str | None = None,
    act_by=None,
    time_text: str | None = None,
    next_action: str | None = None,
    blocked_reason: str | None = None,
    preparation_weeks: int | None = None,
    source_message_id: int | None = None,
    tags: list[str] | None = None,
    review_on=None,
    waiting_for: str | None = None,
    clear_fields: list[str] | None = None,
) -> dict | None:
    # Nur explizit übergebene (nicht-None) Felder werden
    # geändert; alle anderen bleiben unangetastet.

    # Vollständige Validierung vor jeder Datenbankabfrage.
    tags = _validate_tags(tags)
    review_on = parse_date(review_on)
    clear_fields = [] if clear_fields is None else clear_fields
    clearable = {"review_on", "waiting_for", "blocked_reason"}
    if not isinstance(clear_fields, list) or any(
        not isinstance(field, str) or field not in clearable for field in clear_fields
    ):
        raise ValueError("Löschbare Felder: review_on, waiting_for, blocked_reason.")
    follow_up = {"review_on": review_on, "waiting_for": waiting_for, "blocked_reason": blocked_reason}
    if any(follow_up[field] is not None for field in clear_fields):
        raise ValueError("Ein Feld kann nicht zugleich gesetzt und entfernt werden.")
    status = _validate_status(status)
    if status in CLOSED_STATUSES:
        clear_fields = list(clearable)
        follow_up = {field: None for field in clearable}
    priority = _validate_priority(priority)
    deadline = _parse_deadline(deadline)
    event_start = parse_date(event_start)
    event_end = parse_date(event_end)
    time_precision = _validate_time_precision(time_precision)
    act_by = parse_date(act_by)

    sets: list[str] = []
    params: list = []
    for field, value in follow_up.items():
        if field in clear_fields or value is not None:
            sets.append(f"{field} = %s")
            params.append(None if field in clear_fields else value)

    if title is not None:
        sets.append("title = %s")
        params.append(title)
    if description is not None:
        sets.append("description = %s")
        params.append(description)
    if status is not None:
        sets.append("status = %s")
        params.append(status)
    if priority is not None:
        sets.append("priority = %s")
        params.append(priority)
    if deadline is not None:
        sets.append("deadline = %s")
        params.append(deadline)
    if event_start is not None:
        sets.append("event_start = %s")
        params.append(event_start)
    if event_end is not None:
        sets.append("event_end = %s")
        params.append(event_end)
    if time_precision is not None:
        sets.append("time_precision = %s")
        params.append(time_precision)
    if act_by is not None:
        sets.append("act_by = %s")
        params.append(act_by)
    if time_text is not None:
        sets.append("time_text = %s")
        params.append(time_text)
    if next_action is not None:
        sets.append("next_action = %s")
        params.append(next_action)
    if preparation_weeks is not None:
        sets.append("preparation_weeks = %s")
        params.append(preparation_weeks)

    if not sets and tags is None:
        raise ValueError("Keine Änderungen übergeben.")

    with get_connection() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # Aktuelle Werte laden: Existenz prüfen, Embedding
            # bei Titel-/Beschreibungsänderung neu berechnen
            # und Zeiträume bei Teil-Updates korrekt gegen
            # die gespeicherten Werte validieren.
            cur.execute(
                f"SELECT {COLUMNS}"
                " FROM threads WHERE id = %s FOR UPDATE",
                (thread_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            before = _row_to_dict(row)

            if tags is not None:
                _set_tags(cur, thread_id, tags)

            if event_start is not None or event_end is not None:
                new_start = (
                    event_start
                    if event_start is not None
                    else before["event_start"]
                )
                new_end = (
                    event_end
                    if event_end is not None
                    else before["event_end"]
                )
                _validate_event_range(new_start, new_end)

            if title is not None or description is not None:
                new_title = title if title is not None else before["title"]
                new_description = (
                    description
                    if description is not None
                    else before["description"]
                )
                sets.append("embedding = %s")
                params.append(
                    _embed_thread(new_title, new_description)
                )

            sets.append("updated_at = NOW()")
            params.append(thread_id)

            cur.execute(
                f"""
                UPDATE threads
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING {COLUMNS}
                """,
                params,
            )
            updated = cur.fetchone()
            if status in CLOSED_STATUSES or {"waiting_for", "blocked_reason"}.intersection(clear_fields):
                cur.execute(
                    """UPDATE suggestions SET status = 'dismissed', deferred_until = NULL,
                       updated_at = NOW() WHERE thread_id = %s AND status IN ('open', 'deferred')""",
                    (thread_id,),
                )
            elif review_on is not None and review_on > today_berlin():
                cur.execute(
                    """UPDATE suggestions SET status = 'deferred', deferred_until = %s,
                       updated_at = NOW() WHERE thread_id = %s AND status = 'open'""",
                    (review_on, thread_id),
                )
            _link_message(cur, thread_id, source_message_id)
            after = _row_to_dict(updated)
            record_thread_event(
                cur, before, after, source_message_id=source_message_id,
                automatic_fields=clearable if status in CLOSED_STATUSES else (),
            )
            return after
