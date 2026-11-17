"""Cross-process evaluation exclusion and durable daily schedule checks."""

from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from app import settings
from app.storage.database import get_connection

LOCK_ID = 727976008


@contextmanager
def evaluation_lock():
    # A session lock avoids a long-running transaction during model calls.
    # Closing the dedicated connection releases it, including on exceptions.
    with get_connection() as conn:
        conn.autocommit = True
        acquired = conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]
        yield conn if acquired else None


def scheduled_due(conn, now=None):
    now = (now or datetime.now(ZoneInfo("Europe/Berlin"))).astimezone(ZoneInfo("Europe/Berlin"))
    values = settings.current()["values"]
    if (now.hour, now.minute) < (int(values["SCHEDULER_HOUR"]), int(values["SCHEDULER_MINUTE"])):
        return False
    # One attempt per Berlin day, even after a failure/crash. No costly retry storm.
    return not conn.execute(
        "SELECT EXISTS (SELECT 1 FROM evaluation_runs WHERE trigger_source = 'scheduled' "
        "AND (started_at AT TIME ZONE 'Europe/Berlin')::date = %s)",
        (now.date(),),
    ).fetchone()[0]


def latest_review_cursor():
    with get_connection() as conn:
        row = conn.execute("SELECT review_cursor FROM evaluation_runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1").fetchone()
        return row[0] if row else 0
