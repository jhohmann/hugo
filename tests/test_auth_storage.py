"""Auth persistence against PostgreSQL in an isolated, disposable schema."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app.storage import auth
from app.storage.database import DATABASE_URL


@pytest.fixture
def database(monkeypatch):
    try:
        admin = psycopg.connect(DATABASE_URL, connect_timeout=2, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL nicht erreichbar")
    schema = "test_auth_" + uuid4().hex
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        def connection():
            return psycopg.connect(DATABASE_URL, connect_timeout=2, options=f"-c search_path={schema},public")
        monkeypatch.setattr(auth, "get_connection", connection)
        with connection() as conn:
            migration = Path(__file__).parents[1] / "backend/migrations/001_initial.sql"
            conn.execute(migration.read_text(encoding="utf-8"))
            conn.execute(migration.read_text(encoding="utf-8"))  # repeatable upgrade
        yield connection
    finally:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def test_session_persistence_expiry_and_revocation(database):
    token = auth.create_session("password-version-1", 3600)
    another = auth.create_session("password-version-1", 3600)
    assert auth.valid_session(token, "password-version-1")
    assert not auth.valid_session(token, "password-version-2")
    assert not auth.valid_session(token[:-1] + ("a" if token[-1] != "a" else "b"), "password-version-1")
    with database() as conn:
        stored = conn.execute("SELECT token_hash FROM auth_sessions").fetchall()
        assert all(len(row[0]) == 64 and row[0] != token for row in stored)
    auth.delete_session(token)
    assert not auth.valid_session(token, "password-version-1")
    assert auth.valid_session(another, "password-version-1")
    with database() as conn:
        conn.execute("UPDATE auth_sessions SET expires_at = NOW() - INTERVAL '1 second'")
    assert not auth.valid_session(another, "password-version-1")
    fresh = auth.create_session("password-version-1", 3600)
    with database() as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 1
    auth.create_session("password-version-2", 3600)
    assert not auth.valid_session(fresh, "password-version-1")


def test_login_limit_is_atomic_and_recovers(database):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: auth.allow_login_attempt(), range(16)))
    assert sum(results) == 10
    assert not auth.allow_login_attempt()
    with database() as conn:
        conn.execute("UPDATE auth_login_limit SET window_start = NOW() - INTERVAL '61 seconds'")
    assert auth.allow_login_attempt()


def test_http_login_persistence_expiry_and_logout(database, monkeypatch):
    """Real application routes and PostgreSQL, without replacing auth storage."""
    from fastapi.testclient import TestClient

    from app import auth as http_auth
    from app.main import app
    from app.passwords import hash_password

    password = "Temporary integration test password"
    monkeypatch.setenv("HUGO_PASSWORD_HASH", hash_password(password))
    monkeypatch.setenv("HUGO_COOKIE_SECURE", "true")
    client_options = {
        "base_url": "https://testserver",
        "headers": {"Origin": "https://testserver"},
        "follow_redirects": False,
    }
    with TestClient(app, **client_options) as client:
        assert client.get("/").status_code == 401
        assert client.post("/ui/login", data={"password": "wrong"}).status_code == 401
        response = client.post("/ui/login", data={"password": password, "remember": "true"})
        assert response.status_code == 303
        assert "Max-Age=2592000" in response.headers["set-cookie"]
        assert client.cookies[http_auth.COOKIE]
        assert client.get("/").status_code == 200
        with database() as conn:
            remaining = conn.execute(
                "SELECT EXTRACT(EPOCH FROM expires_at - NOW()) FROM auth_sessions"
            ).fetchone()[0]
            assert http_auth.REMEMBER_SECONDS - 60 < remaining <= http_auth.REMEMBER_SECONDS

    # A new HTTP client can authenticate using the persisted token.
    with TestClient(app, cookies=client.cookies, **client_options) as reopened:
        assert reopened.get("/").status_code == 200
        with database() as conn:
            conn.execute("UPDATE auth_sessions SET expires_at = NOW() - INTERVAL '1 second'")
        assert reopened.get("/").status_code == 401
        assert reopened.post("/ui/login", data={"password": password}).status_code == 303
        new_token = reopened.cookies[http_auth.COOKIE]
        assert reopened.post("/ui/logout").status_code == 303
        with database() as conn:
            assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
        reopened.cookies.set(http_auth.COOKIE, new_token)
        assert reopened.get("/").status_code == 401


@pytest.mark.parametrize("token", ["", "bad", "ä" * 43, "!" * 43, "a" * 44])
def test_malformed_token_never_queries_database(monkeypatch, token):
    monkeypatch.setattr(auth, "get_connection", lambda: pytest.fail("Malformed token queried DB"))
    assert not auth.valid_session(token, "configured-password")
