"""Speicherung der Google-OAuth-Tokens und OAuth-States.

Single-User: genau eine Credentials-Zeile (id = 1).
Tokens liegen ausschließlich in der Datenbank, nie im
Repository, und werden niemals an das Sprachmodell
weitergegeben.
"""

from datetime import datetime, timezone

from app.storage.database import get_connection


def save_credentials(
    access_token: str,
    refresh_token: str,
    expires_at: datetime,
    scopes: str,
) -> None:
    """Legt die Credentials an oder ersetzt sie (Reconnect)."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO google_credentials
                    (id, access_token, refresh_token,
                     expires_at, scopes)
                VALUES (1, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    expires_at = EXCLUDED.expires_at,
                    scopes = EXCLUDED.scopes,
                    updated_at = NOW()
                """,
                (access_token, refresh_token, expires_at, scopes),
            )


def get_credentials() -> dict | None:
    """Aktuelle Credentials oder None, wenn nicht verbunden."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT access_token, refresh_token,
                       expires_at, scopes, connected_at
                FROM google_credentials
                WHERE id = 1
                """
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "access_token": row[0],
        "refresh_token": row[1],
        "expires_at": row[2],
        "scopes": row[3],
        "connected_at": row[4],
    }


def update_access_token(access_token: str, expires_at: datetime) -> None:
    """Nur das Access-Token nach einem Refresh ersetzen."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE google_credentials
                SET access_token = %s,
                    expires_at = %s,
                    updated_at = NOW()
                WHERE id = 1
                """,
                (access_token, expires_at),
            )


def delete_credentials() -> bool:
    """Verbindung trennen. True, wenn eine Zeile entfernt wurde."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM google_credentials WHERE id = 1")
            return cur.rowcount > 0


def save_oauth_state(state: str) -> None:
    """State für den OAuth-Flow ablegen (CSRF-Schutz)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Alte States aufräumen (älter als 1 Stunde).
            cur.execute(
                """
                DELETE FROM google_oauth_states
                WHERE created_at < NOW() - INTERVAL '1 hour'
                """
            )
            cur.execute(
                """
                INSERT INTO google_oauth_states (state)
                VALUES (%s)
                ON CONFLICT (state) DO NOTHING
                """,
                (state,),
            )


def consume_oauth_state(state: str) -> bool:
    """State prüfen und löschen. True = gültig (genau einmal)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM google_oauth_states
                WHERE state = %s
                """,
                (state,),
            )
            return cur.rowcount > 0
