from datetime import datetime, timezone

from pgvector.psycopg import register_vector

from app.storage.database import get_connection
from app.storage.embeddings import (
    embed_document,
    embed_query,
)
from app.tools.dates import parse_date

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

MIN_PRIORITY = 1
MAX_PRIORITY = 5

COLUMNS = (
    "id, title, description, status, priority,"
    " deadline, event_start, event_end, time_precision,"
    " act_by, time_text, next_action, created_at, updated_at"
)

# Genauigkeit der Zeitangabe:
# exact       = exakter Termin oder genau bekannter Zeitraum
# approximate = ungefähre Angabe (z. B. 'Mitte Juni');
#               die Originalangabe steht in time_text
TIME_PRECISIONS = ("exact", "approximate")


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
        "created_at": row[12],
        "updated_at": row[13],
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
    source_message_id: int | None = None,
) -> int:
    status = _validate_status(status) or "proposed"
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
                     next_action, embedding)
                VALUES (%s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    title, description, status, priority,
                    deadline, event_start, event_end,
                    time_precision, act_by, time_text,
                    next_action, embedding,
                ),
            )
            thread_id = cur.fetchone()[0]
            _link_message(cur, thread_id, source_message_id)
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
) -> list[dict]:
    status = _validate_status(status)

    where = ""
    params: list = []
    if open_only:
        where = "WHERE status NOT IN ('completed', 'archived')"
    elif status is not None:
        where = "WHERE status = %s"
        params.append(status)
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
                    COALESCE(act_by, event_start, deadline::date)
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
) -> list[dict]:
    status = _validate_status(status)
    embedding = embed_query(query)

    # Platzhalter-Reihenfolge im SQL beachten:
    # 1. Similarity im SELECT, 2. optionaler Status im WHERE,
    # 3. Embedding im ORDER BY, 4. LIMIT.
    where = "embedding IS NOT NULL"
    params: list = [embedding]
    if status is not None:
        where += " AND status = %s"
        params.append(status)
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
                thread = _row_to_dict(row[:14])
                thread["similarity"] = round(float(row[14]), 3)
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
    source_message_id: int | None = None,
) -> dict | None:
    # Nur explizit übergebene (nicht-None) Felder werden
    # geändert; alle anderen bleiben unangetastet.

    # Vollständige Validierung vor jeder Datenbankabfrage.
    status = _validate_status(status)
    priority = _validate_priority(priority)
    deadline = _parse_deadline(deadline)
    event_start = parse_date(event_start)
    event_end = parse_date(event_end)
    time_precision = _validate_time_precision(time_precision)
    act_by = parse_date(act_by)

    sets: list[str] = []
    params: list = []

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

    if not sets:
        raise ValueError("Keine Änderungen übergeben.")

    with get_connection() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # Aktuelle Werte laden: Existenz prüfen, Embedding
            # bei Titel-/Beschreibungsänderung neu berechnen
            # und Zeiträume bei Teil-Updates korrekt gegen
            # die gespeicherten Werte validieren.
            cur.execute(
                "SELECT title, description, event_start, event_end"
                " FROM threads WHERE id = %s",
                (thread_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            if event_start is not None or event_end is not None:
                new_start = (
                    event_start
                    if event_start is not None
                    else row[2]
                )
                new_end = (
                    event_end
                    if event_end is not None
                    else row[3]
                )
                _validate_event_range(new_start, new_end)

            if title is not None or description is not None:
                new_title = title if title is not None else row[0]
                new_description = (
                    description
                    if description is not None
                    else row[1]
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
            _link_message(cur, thread_id, source_message_id)
            return _row_to_dict(updated) if updated else None
