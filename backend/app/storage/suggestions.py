"""Speicherung proaktiver Vorschläge und Evaluationsläufe."""

from app.storage.database import get_connection
from app.tools.dates import parse_date, today_berlin

# Bearbeitungsstatus eines Vorschlags:
# open      = neu, noch nicht vom Nutzer behandelt
# confirmed = vom Nutzer bestätigt / angenommen
# deferred  = zurückgestellt (später)
# dismissed = verworfen
SUGGESTION_STATUSES = ("open", "confirmed", "deferred", "dismissed")

# Zustellstatus:
# pending  = erzeugt, dem Nutzer noch nicht gezeigt
# surfaced = dem Nutzer gezeigt (aktuell über GET /suggestions)
DELIVERY_STATUSES = ("pending", "surfaced")

RUN_TRIGGERS = ("manual", "scheduled")

MIN_PRIORITY = 1
MAX_PRIORITY = 5

COLUMNS = (
    "id, thread_id, run_id, content, reason, priority,"
    " suggested_date, delivery_status, status,"
    " created_at, updated_at, deferred_until"
)

RUN_COLUMNS = (
    "id, trigger_source, status, threads_considered,"
    " suggestions_created, error, started_at, finished_at"
)


def _validate_status(status):
    if status not in SUGGESTION_STATUSES:
        raise ValueError(
            f"Ungültiger Vorschlags-Status: {status!r}."
            f" Erlaubt: {', '.join(SUGGESTION_STATUSES)}"
        )
    return status


def _validate_delivery(delivery):
    if delivery not in DELIVERY_STATUSES:
        raise ValueError(
            f"Ungültiger Zustellstatus: {delivery!r}."
            f" Erlaubt: {', '.join(DELIVERY_STATUSES)}"
        )
    return delivery


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


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "thread_id": row[1],
        "run_id": row[2],
        "content": row[3],
        "reason": row[4],
        "priority": row[5],
        "suggested_date": row[6],
        "delivery_status": row[7],
        "status": row[8],
        "created_at": row[9],
        "updated_at": row[10],
        "deferred_until": row[11],
    }


def _run_to_dict(row) -> dict:
    return {
        "id": row[0],
        "trigger_source": row[1],
        "status": row[2],
        "threads_considered": row[3],
        "suggestions_created": row[4],
        "error": row[5],
        "started_at": row[6],
        "finished_at": row[7],
    }


# --- Evaluationsläufe ---

def create_run(trigger: str = "manual") -> int:
    if trigger not in RUN_TRIGGERS:
        raise ValueError(
            f"Ungültiger Trigger: {trigger!r}."
            f" Erlaubt: {', '.join(RUN_TRIGGERS)}"
        )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_runs (trigger_source)
                VALUES (%s)
                RETURNING id
                """,
                (trigger,),
            )
            return cur.fetchone()[0]


def finish_run(
    run_id: int,
    *,
    status: str,
    threads_considered: int | None = None,
    suggestions_created: int | None = None,
    error: str | None = None,
) -> None:
    if status not in ("completed", "failed"):
        raise ValueError(
            f"Ungültiger Lauf-Status: {status!r}."
            " Erlaubt: completed, failed"
        )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE evaluation_runs
                SET status = %s,
                    finished_at = NOW(),
                    threads_considered = %s,
                    suggestions_created = %s,
                    error = %s
                WHERE id = %s
                """,
                (
                    status,
                    threads_considered,
                    suggestions_created,
                    error,
                    run_id,
                ),
            )


def list_runs(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {RUN_COLUMNS}
                FROM evaluation_runs
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [_run_to_dict(row) for row in cur.fetchall()]


# --- Vorschläge ---

def _reactivate_due(cur):
    """Reactivate once, using the user's Berlin date rather than DB timezone."""
    today = today_berlin()
    cur.execute(
        """UPDATE suggestions s
           SET status = 'open', deferred_until = NULL,
               delivery_status = 'pending', updated_at = NOW()
           WHERE status = 'deferred' AND deferred_until <= %s
             AND NOT EXISTS (
                 SELECT 1 FROM threads t WHERE t.id = s.thread_id
                 AND (t.status IN ('completed', 'archived') OR t.review_on > %s)
             )""",
        (today, today),
    )


def create_suggestion(
    thread_id: int | None,
    content: str,
    reason: str | None = None,
    priority: int | None = None,
    suggested_date=None,
    run_id: int | None = None,
) -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("Leerer Vorschlagstext.")
    priority = _validate_priority(priority)
    suggested_date = parse_date(suggested_date)

    with get_connection() as conn:
        with conn.cursor() as cur:
            if thread_id is not None:
                cur.execute(
                    "SELECT status, review_on FROM threads WHERE id = %s FOR UPDATE",
                    (thread_id,),
                )
                thread = cur.fetchone()
                if thread is None:
                    raise ValueError(
                        f"Thread nicht gefunden: {thread_id}"
                    )
                if thread[0] in ("completed", "archived"):
                    return {"created": False, "reason": "thread_closed"}
                if thread[1] is not None and thread[1] > today_berlin():
                    return {"created": False, "reason": "review_not_due"}
                cur.execute(
                    """SELECT id FROM suggestions WHERE thread_id = %s
                       AND status = 'deferred'
                       AND (deferred_until IS NULL OR deferred_until > %s)
                       LIMIT 1""",
                    (thread_id, today_berlin()),
                )
                deferred = cur.fetchone()
                if deferred is not None:
                    return {"created": False, "reason": "deferred", "suggestion_id": deferred[0]}

            # Keine identischen Vorschläge wiederholen —
            # weder innerhalb eines Laufs noch über Läufe
            # hinweg, unabhängig vom Bearbeitungsstatus.
            cur.execute(
                """
                SELECT id
                FROM suggestions
                WHERE thread_id IS NOT DISTINCT FROM %s
                  AND lower(trim(content)) = lower(trim(%s))
                LIMIT 1
                """,
                (thread_id, content),
            )
            duplicate = cur.fetchone()
            if duplicate is not None:
                return {
                    "suggestion_id": duplicate[0],
                    "created": False,
                    "reason": "duplicate",
                }

            cur.execute(
                """
                INSERT INTO suggestions
                    (thread_id, run_id, content, reason,
                     priority, suggested_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    thread_id, run_id, content, reason,
                    priority, suggested_date,
                ),
            )
            return {
                "suggestion_id": cur.fetchone()[0],
                "created": True,
            }


def list_suggestions(
    status: str | None = None,
    delivery: str | None = None,
    limit: int = 100,
    mark_surfaced: bool = False,
    thread_id: int | None = None,
) -> list[dict]:
    conditions = []
    params: list = []
    if thread_id is not None:
        conditions.append("thread_id = %s")
        params.append(thread_id)
    if status is not None:
        _validate_status(status)
        conditions.append("status = %s")
        params.append(status)
    if delivery is not None:
        _validate_delivery(delivery)
        conditions.append("delivery_status = %s")
        params.append(delivery)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            _reactivate_due(cur)
            cur.execute(
                f"""
                SELECT {COLUMNS}
                FROM suggestions
                {where}
                ORDER BY
                    priority DESC NULLS LAST,
                    created_at DESC
                LIMIT %s
                """,
                params,
            )
            suggestions = [
                _row_to_dict(row) for row in cur.fetchall()
            ]

            # Gelesene Vorschläge gelten als zugestellt.
            if mark_surfaced:
                pending_ids = [
                    s["id"]
                    for s in suggestions
                    if s["delivery_status"] == "pending" and s["status"] == "open"
                ]
                if pending_ids:
                    cur.execute(
                        """
                        UPDATE suggestions
                        SET delivery_status = 'surfaced',
                            updated_at = NOW()
                        WHERE id = ANY(%s)
                        """,
                        (pending_ids,),
                    )
                    for s in suggestions:
                        if s["id"] in pending_ids:
                            s["delivery_status"] = "surfaced"

            return suggestions


def count_suggestions_for_run(run_id: int) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM suggestions WHERE run_id = %s",
                (run_id,),
            )
            return cur.fetchone()[0]


def update_suggestion_status(
    suggestion_id: int,
    status: str,
    deferred_until=None,
) -> dict | None:
    _validate_status(status)
    deferred_until = parse_date(deferred_until)
    if deferred_until is not None:
        if status != "deferred":
            raise ValueError("Ein Wiedervorlagedatum ist nur beim Zurückstellen erlaubt.")
        if deferred_until <= today_berlin():
            raise ValueError("Bitte ein zukünftiges Wiedervorlagedatum wählen.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Lock the thread before its suggestion, matching create/update_thread.
            cur.execute("SELECT thread_id FROM suggestions WHERE id = %s", (suggestion_id,))
            target = cur.fetchone()
            if target is None:
                return None
            if target[0] is not None:
                cur.execute("SELECT status FROM threads WHERE id = %s FOR UPDATE", (target[0],))
                thread = cur.fetchone()
                if thread and thread[0] in ("completed", "archived") and status in ("open", "deferred"):
                    raise ValueError("Ein abgeschlossenes Vorhaben kann nicht wieder vorgelegt werden.")
            cur.execute("SELECT status FROM suggestions WHERE id = %s FOR UPDATE", (suggestion_id,))
            current = cur.fetchone()
            if current is None:
                return None
            if status == "deferred" and current[0] not in ("open", "deferred"):
                raise ValueError("Nur offene oder zurückgestellte Vorschläge können zurückgestellt werden.")
            cur.execute(
                f"""
                UPDATE suggestions
                SET status = %s, deferred_until = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING {COLUMNS}
                """,
                (status, deferred_until, suggestion_id),
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
