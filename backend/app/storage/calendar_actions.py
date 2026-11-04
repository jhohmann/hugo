"""Ausstehende Kalenderaktionen und Aktionsprotokoll.

Der Agent erzeugt hier ausschließlich Vorschläge
(status='pending'). Statusübergänge sind in SQL gegen
doppelte Ausführung abgesichert (WHERE-Status-Guard).
"""

import json

from app.storage.database import get_connection

ACTION_TYPES = ("create", "update", "delete")

ACTION_STATUSES = (
    "pending",
    "confirmed",
    "rejected",
    "executed",
    "failed",
    "conflict",
)

# Status, aus denen eine Bestätigung bzw. Ablehnung möglich ist.
CONFIRMABLE_STATUSES = ("pending", "conflict")

COLUMNS = (
    "id, action_type, calendar_id, event_id, payload,"
    " snapshot, status, result, error, source_message_id,"
    " created_at, updated_at, executed_at"
)


def _json(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "action_type": row[1],
        "calendar_id": row[2],
        "event_id": row[3],
        "payload": row[4],
        "snapshot": row[5],
        "status": row[6],
        "result": row[7],
        "error": row[8],
        "source_message_id": row[9],
        "created_at": row[10],
        "updated_at": row[11],
        "executed_at": row[12],
    }


def create_action(
    action_type: str,
    calendar_id: str,
    payload: dict,
    event_id: str | None = None,
    snapshot: dict | None = None,
    source_message_id: int | None = None,
) -> int:
    """Neue ausstehende Aktion. Liefert die Aktions-ID."""
    if action_type not in ACTION_TYPES:
        raise ValueError(
            f"Ungültiger Aktionstyp: {action_type!r}."
            f" Erlaubt: {', '.join(ACTION_TYPES)}"
        )
    if action_type in ("update", "delete") and not event_id:
        raise ValueError(
            f"{action_type} benötigt eine event_id."
        )
    if action_type in ("update", "delete") and snapshot is None:
        raise ValueError(
            f"{action_type} benötigt einen Snapshot des Termins."
        )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calendar_actions
                    (action_type, calendar_id, event_id,
                     payload, snapshot, source_message_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    action_type,
                    calendar_id,
                    event_id,
                    _json(payload),
                    _json(snapshot),
                    source_message_id,
                ),
            )
            return cur.fetchone()[0]


def get_action(action_id: int) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {COLUMNS} FROM calendar_actions WHERE id = %s",
                (action_id,),
            )
            row = cur.fetchone()
    return _row_to_dict(row) if row else None


def list_actions(
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Aktionen, optional nach Status gefiltert, neueste zuerst."""
    if status is not None and status not in ACTION_STATUSES:
        raise ValueError(
            f"Ungültiger Aktionsstatus: {status!r}."
            f" Erlaubt: {', '.join(ACTION_STATUSES)}"
        )
    with get_connection() as conn:
        with conn.cursor() as cur:
            if status is None:
                cur.execute(
                    f"SELECT {COLUMNS} FROM calendar_actions"
                    " ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
            else:
                cur.execute(
                    f"SELECT {COLUMNS} FROM calendar_actions"
                    " WHERE status = %s ORDER BY id DESC LIMIT %s",
                    (status, limit),
                )
            return [_row_to_dict(row) for row in cur.fetchall()]


def count_pending_actions() -> int:
    """Anzahl offener Aktionen (pending + Konflikte) für die UI."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM calendar_actions
                WHERE status IN ('pending', 'conflict')
                """
            )
            return cur.fetchone()[0]


def try_mark_confirmed(action_id: int) -> bool:
    """pending/conflict → confirmed, genau einmal möglich.

    False, wenn die Aktion bereits anderweitig behandelt wurde
    (Schutz gegen doppelte Bestätigung/Ausführung).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE calendar_actions
                SET status = 'confirmed', updated_at = NOW()
                WHERE id = %s AND status IN ('pending', 'conflict')
                """,
                (action_id,),
            )
            return cur.rowcount > 0


def mark_conflict(action_id: int, current_event: dict) -> None:
    """confirmed → conflict: Termin wurde seit dem Vorschlag
    verändert; der aktuelle Stand wird in result abgelegt."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE calendar_actions
                SET status = 'conflict',
                    result = %s,
                    updated_at = NOW()
                WHERE id = %s AND status = 'confirmed'
                """,
                (_json(current_event), action_id),
            )


def mark_executed(action_id: int, result: dict) -> None:
    """confirmed → executed nach erfolgreicher API-Ausführung."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE calendar_actions
                SET status = 'executed',
                    result = %s,
                    error = NULL,
                    executed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s AND status = 'confirmed'
                """,
                (_json(result), action_id),
            )


def mark_failed(action_id: int, error: str) -> None:
    """confirmed → failed bei Fehlern der Ausführung."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE calendar_actions
                SET status = 'failed',
                    error = %s,
                    updated_at = NOW()
                WHERE id = %s AND status = 'confirmed'
                """,
                (error, action_id),
            )


def try_mark_rejected(action_id: int) -> bool:
    """pending/conflict → rejected, genau einmal möglich."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE calendar_actions
                SET status = 'rejected', updated_at = NOW()
                WHERE id = %s AND status IN ('pending', 'conflict')
                """,
                (action_id,),
            )
            return cur.rowcount > 0


def log_action(
    action_id: int | None,
    action_type: str,
    calendar_id: str,
    event_id: str | None,
    summary: str | None,
    detail: dict | None = None,
) -> int:
    """Eintrag im internen Aktionsprotokoll.

    Dokumentiert insbesondere Löschungen, weil die
    Terminbeschreibung nach dem Löschen nicht mehr
    verfügbar ist.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calendar_action_log
                    (action_id, action_type, calendar_id,
                     event_id, summary, detail)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    action_id,
                    action_type,
                    calendar_id,
                    event_id,
                    summary,
                    _json(detail),
                ),
            )
            return cur.fetchone()[0]


def list_action_log(limit: int = 50) -> list[dict]:
    """Jüngste Protokolleinträge, neueste zuerst."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, action_id, action_type, calendar_id,
                       event_id, summary, detail, created_at
                FROM calendar_action_log
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {
                    "id": row[0],
                    "action_id": row[1],
                    "action_type": row[2],
                    "calendar_id": row[3],
                    "event_id": row[4],
                    "summary": row[5],
                    "detail": row[6],
                    "created_at": row[7],
                }
                for row in cur.fetchall()
            ]
