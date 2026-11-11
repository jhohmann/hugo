"""Serialize registration changes and rotating refresh tokens across processes."""

from contextlib import contextmanager
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.storage.database import get_connection


@contextmanager
def locked_registration():
    with get_connection() as conn:
        conn.execute("SET LOCAL lock_timeout = '35s'")
        conn.execute("SELECT pg_advisory_xact_lock(727976007)")
        conn.execute(
            "INSERT INTO model_oauth (id, host_id) VALUES (1, %s) ON CONFLICT DO NOTHING",
            ("urn:uuid:" + str(uuid4()),),
        )
        host_id, registration = conn.execute(
            "SELECT host_id, registration FROM model_oauth WHERE id = 1"
        ).fetchone()
        before = dict(registration)
        yield host_id, registration
        if registration != before:
            conn.execute(
                "UPDATE model_oauth SET registration = %s, updated_at = NOW() WHERE id = 1",
                (Jsonb(registration),),
            )


def read_registration():
    with locked_registration() as (host_id, registration):
        return host_id, dict(registration)
