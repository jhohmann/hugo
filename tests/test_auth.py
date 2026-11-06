"""HTTP authentication boundary; no real database or model calls."""

import secrets

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app
from app.passwords import hash_password, verify_password

PASSWORD = "Ein langes Testpasswort ä!"


@pytest.fixture(scope="module")
def encoded_password():
    return hash_password(PASSWORD)


@pytest.fixture
def sessions(monkeypatch, encoded_password):
    monkeypatch.setenv("HUGO_PASSWORD_HASH", encoded_password)
    monkeypatch.setenv("HUGO_COOKIE_SECURE", "true")
    state = {}

    def create(encoded, lifetime):
        token = secrets.token_urlsafe(32)
        state[token] = (encoded, lifetime)
        return token

    monkeypatch.setattr(auth.storage, "create_session", create)
    monkeypatch.setattr(auth.storage, "valid_session", lambda token, encoded: token in state and state[token][0] == encoded)
    monkeypatch.setattr(auth.storage, "delete_session", lambda token: state.pop(token, None))
    monkeypatch.setattr(auth.storage, "allow_login_attempt", lambda: True)
    return state


@pytest.fixture
def client(sessions):
    with TestClient(app, base_url="https://testserver", headers={"Origin": "https://testserver"}, follow_redirects=False) as client:
        yield client


def login(client, **extra):
    return client.post("/ui/login", data={"password": PASSWORD, **extra})


@pytest.mark.parametrize("path", ["/", "/memories", "/threads", "/conversations", "/conversations/1/messages", "/suggestions", "/proactivity/runs", "/calendar/status", "/calendar/actions", "/docs", "/redoc", "/openapi.json"])
def test_api_requires_login(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/chat", "/proactivity/evaluate", "/calendar/actions/1/confirm", "/calendar/actions/1/reject", "/calendar/disconnect"])
def test_mutations_require_login(client, path):
    assert client.post(path).status_code == 401
    assert client.patch("/suggestions/1", json={"status": "confirmed"}).status_code == 401


def test_ui_redirect_and_public_pages(client):
    response = client.get("/ui/chat/7")
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login?next=%2Fui%2Fchat%2F7"
    response = client.get(response.headers["location"])
    assert response.status_code == 200
    assert 'name="password"' in response.text
    assert 'name="username"' not in response.text
    assert "Abmelden" not in response.text
    assert client.get("/health").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_wrong_password_creates_no_session(client, sessions):
    response = client.post("/ui/login", data={"password": "wrong"})
    assert response.status_code == 401
    assert "nicht richtig" in response.text
    assert "set-cookie" not in response.headers
    assert sessions == {}


@pytest.mark.parametrize("remember,lifetime", [(False, auth.SESSION_SECONDS), (True, auth.REMEMBER_SECONDS)])
def test_login_cookie_and_api_access(client, sessions, remember, lifetime):
    response = login(client, remember=str(remember).lower(), next="/ui/chat/7")
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/chat/7"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert ("Max-Age=2592000" in cookie) == remember
    assert next(iter(sessions.values()))[1] == lifetime
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    # A fresh client represents a reopened browser/server process: same stored token.
    with TestClient(app, base_url="https://testserver", cookies=dict(client.cookies)) as reopened:
        assert reopened.get("/").status_code == 200


def test_logout_revokes_token(client, sessions):
    login(client)
    token = client.cookies[auth.COOKIE]
    response = client.post("/ui/logout")
    assert response.status_code == 303
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert sessions == {}
    client.cookies.set(auth.COOKIE, token)
    assert client.get("/").status_code == 401


def test_password_rotation_invalidates_session(client, monkeypatch):
    login(client)
    monkeypatch.setenv("HUGO_PASSWORD_HASH", hash_password("Ein anderes langes Passwort"))
    assert client.get("/").status_code == 401


def test_new_login_rotates_session(client, sessions):
    login(client)
    old = client.cookies[auth.COOKIE]
    login(client)
    assert old not in sessions
    assert len(sessions) == 1


@pytest.mark.parametrize("target", ["https://evil.example", "//evil.example", "/ui/\\evil", "/ui/login", "/ui/logout", "/ui/\r\nevil"])
def test_login_blocks_external_redirects(client, target):
    assert login(client, next=target).headers["location"] == "/ui/heute"


@pytest.mark.parametrize("origin", ["https://evil.example", "https://testserver.evil.example", "http://testserver", "null"])
def test_csrf_rejected_on_login_and_authenticated_writes(client, origin):
    assert client.post("/ui/login", data={"password": PASSWORD}, headers={"Origin": origin}).status_code == 403
    login(client)
    assert client.post("/calendar/disconnect", headers={"Origin": origin}).status_code == 403
    assert client.post("/ui/logout", headers={"Origin": origin}).status_code == 403


def test_missing_origin_requires_explicit_cli_header(client):
    client.headers.pop("Origin")
    assert login(client).status_code == 403
    client.headers["X-Hugo-Request"] = "1"
    assert login(client).status_code == 303
    client.headers["Origin"] = "https://evil.example"
    assert client.post("/ui/logout").status_code == 403


def test_same_origin_referer_fallback(client):
    client.headers.pop("Origin")
    client.headers["Referer"] = "https://testserver/ui/login"
    assert login(client).status_code == 303


def test_throttled_before_password_verification(client, monkeypatch, sessions):
    monkeypatch.setattr(auth.storage, "allow_login_attempt", lambda: False)
    monkeypatch.setattr(auth, "verify_password", lambda *_: pytest.fail("Must throttle first"))
    response = login(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert sessions == {}


@pytest.mark.parametrize("configured", ["", "invalid", "scrypt-v1:ab:cd"])
def test_missing_or_malformed_config_fails_closed(client, monkeypatch, configured):
    monkeypatch.setenv("HUGO_PASSWORD_HASH", configured)
    assert client.get("/memories").status_code == 503
    assert client.get("/ui/login").status_code == 503
    assert login(client).status_code == 503
    assert client.get("/health").status_code == 200


def test_database_failure_fails_closed(client, monkeypatch):
    def unavailable(*_):
        raise psycopg.OperationalError("secret connection details")
    monkeypatch.setattr(auth.storage, "valid_session", unavailable)
    response = client.get("/memories")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_http_development_cookie_opt_in(client, monkeypatch):
    monkeypatch.setenv("HUGO_COOKIE_SECURE", "false")
    assert "Secure" not in login(client).headers["set-cookie"]


def test_password_hashing(encoded_password):
    assert PASSWORD not in encoded_password
    assert hash_password(PASSWORD) != encoded_password
    assert verify_password(PASSWORD, encoded_password)
    assert not verify_password("incorrect", encoded_password)
    assert not verify_password("x" * 1025, encoded_password)
    with pytest.raises(ValueError):
        hash_password("short")
