"""Shared, non-secret application preferences; concurrent forms cannot overwrite."""

from psycopg.types.json import Jsonb

from app.storage.database import get_connection


class SettingsConflict(ValueError):
    pass


def read_settings():
    with get_connection() as conn:
        values, revision, updated = conn.execute(
            "SELECT values, revision, updated_at FROM app_settings WHERE id = 1"
        ).fetchone()
    return {"values": values, "revision": revision, "updated_at": updated}


def save_settings(values, revision):
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE app_settings SET values = %s, revision = revision + 1, updated_at = NOW() "
            "WHERE id = 1 AND revision = %s RETURNING revision",
            (Jsonb(values), revision),
        ).fetchone()
        if result is None:
            raise SettingsConflict("Die Einstellungen wurden inzwischen geändert. Bitte neu laden und erneut bearbeiten.")
    return result[0]
