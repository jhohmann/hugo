from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import auth
from app.main import app
from app.storage import suggestions, threads
from app.web import routes
from app.web.timeline import TimelineData, TimelinePoint, demo_timeline
from test_follow_up import store


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, "password_hash", lambda: "configured")
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: True)
    monkeypatch.setattr(routes, "count_open_suggestions", lambda: 0)
    monkeypatch.setattr(routes, "count_pending_actions", lambda: 0)
    def forbidden(*args, **kwargs):
        raise AssertionError("Timeline must not read through lifecycle functions")
    monkeypatch.setattr(routes, "list_suggestions", forbidden)
    monkeypatch.setattr(routes, "list_threads", forbidden)
    return TestClient(app)


def test_demo_gate_and_empty_live_view(client, monkeypatch):
    monkeypatch.delenv("HUGO_TIMELINE_DEMO", raising=False)
    assert client.get("/ui/zeitleiste?demo=1").status_code == 404
    response = client.get("/ui/zeitleiste")
    assert response.status_code == 200 and "noch nicht angebunden" in response.text
    monkeypatch.setenv("HUGO_TIMELINE_DEMO", "true")
    response = client.get("/ui/zeitleiste?demo=1")
    assert response.status_code == 200
    assert "Beispieldaten" in response.text and "Ohne Datum" in response.text
    assert "Herkunft unbekannt" in response.text and "Vorschlag" in response.text


def test_demo_requires_login(client, monkeypatch):
    monkeypatch.setenv("HUGO_TIMELINE_DEMO", "true")
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: False)
    response = client.get("/ui/zeitleiste?demo=1", follow_redirects=False)
    assert response.status_code == 303
    assert "/ui/login" in response.headers["location"]


def test_demo_escapes_text(client, monkeypatch):
    monkeypatch.setenv("HUGO_TIMELINE_DEMO", "true")
    data = demo_timeline(date(2026, 11, 7))
    data.threads[0].title = "<script>alert(1)</script>"
    monkeypatch.setattr(routes, "demo_timeline", lambda _: data)
    response = client.get("/ui/zeitleiste?demo=1")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_demo_roundtrip():
    data = demo_timeline(date(2026, 11, 7))
    restored = TimelineData.model_validate_json(data.model_dump_json())
    assert restored == data
    assert {p.layer for p in data.points} == {"activity", "planning", "deadline", "idea"}
    assert all(not p.user_activity for p in data.points if p.layer == "idea")
    assert all(p.source_url is None for p in data.points)


@pytest.mark.parametrize("values", [
    {"layer": "idea", "commitment": "confirmed"},
    {"origin": "hugo", "user_activity": True},
    {"start": datetime(2026, 1, 1)},
    {"end": date(2026, 1, 2)},
    {"precision": "exact"},
    {"source_url": "javascript:alert(1)"},
    {"source_url": "//example.com"},
])
def test_invalid_point_semantics(values):
    with pytest.raises(ValidationError):
        TimelinePoint.model_validate({
            "id": "p", "thread_id": "t", "layer": "activity", "time_kind": "recorded",
            "title": "Test", "summary": "Test", **values,
        })


def test_timestamp_preserved_in_json():
    point = TimelinePoint(id="p", thread_id="t", layer="activity", time_kind="recorded",
                          title="Test", summary="Test", start=datetime(2026, 1, 1, tzinfo=timezone.utc))
    restored = TimelinePoint.model_validate_json(point.model_dump_json())
    assert isinstance(restored.start, datetime) and restored.start.utcoffset() is not None


def test_timeline_leaves_due_suggestions_unchanged(store, client, monkeypatch):
    monkeypatch.setenv("HUGO_TIMELINE_DEMO", "true")
    monkeypatch.setattr(routes, "count_open_suggestions", suggestions.count_open_suggestions)
    tid = threads.create_thread("Unverändert")
    sid = suggestions.create_suggestion(tid, "Prüfen")["suggestion_id"]
    with store() as conn:
        conn.execute("UPDATE suggestions SET status='deferred', deferred_until='2020-01-01' WHERE id=%s", (sid,))
        before = conn.execute("SELECT to_jsonb(s) FROM suggestions s ORDER BY id").fetchall()
        event_count = conn.execute("SELECT count(*) FROM thread_events").fetchone()[0]
    assert client.get("/ui/zeitleiste?demo=1").status_code == 200
    assert client.get("/ui/zeitleiste").status_code == 200
    assert suggestions.count_open_suggestions() == 0
    with store() as conn:
        assert conn.execute("SELECT to_jsonb(s) FROM suggestions s ORDER BY id").fetchall() == before
        assert conn.execute("SELECT count(*) FROM thread_events").fetchone()[0] == event_count
        assert conn.execute("SELECT count(*) FROM threads").fetchone()[0] == 1
