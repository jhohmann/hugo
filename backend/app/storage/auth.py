"""Persistente, einzeln widerrufbare Sitzungen ohne Benutzerkonten."""

import hashlib
import secrets

from app.storage.database import get_connection


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def allow_login_attempt() -> bool:
    """Höchstens zehn Versuche pro Minute insgesamt, atomar in PostgreSQL."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO auth_login_limit (id, window_start, attempts)
                VALUES (1, NOW(), 1)
                ON CONFLICT (id) DO UPDATE SET
                    attempts = CASE
                        WHEN auth_login_limit.window_start <= NOW() - INTERVAL '1 minute'
                        THEN 1 ELSE auth_login_limit.attempts + 1 END,
                    window_start = CASE
                        WHEN auth_login_limit.window_start <= NOW() - INTERVAL '1 minute'
                        THEN NOW() ELSE auth_login_limit.window_start END
                RETURNING attempts
            """)
            return cur.fetchone()[0] <= 10


def create_session(password_hash: str, lifetime: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_sessions WHERE expires_at <= NOW() OR password_version <> %s",
                        (_digest(password_hash),))
            cur.execute("""
                INSERT INTO auth_sessions (token_hash, password_version, expires_at)
                VALUES (%s, %s, NOW() + %s * INTERVAL '1 second')
            """, (_digest(token), _digest(password_hash), lifetime))
    return token


def valid_session(token: str, password_hash: str) -> bool:
    if len(token) != 43 or not all(c.isascii() and (c.isalnum() or c in "-_") for c in token):
        return False
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM auth_sessions
                WHERE token_hash = %s AND password_version = %s AND expires_at > NOW()
            """, (_digest(token), _digest(password_hash)))
            return cur.fetchone() is not None


def delete_session(token: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (_digest(token),))
