"""Follow-up lifecycle against disposable PostgreSQL databases; no model calls."""

from datetime import date, datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app import auth, migrate
from app.agent import assistant, evaluation
from app.main import app
from app.storage import database, suggestions, threads
from app.tools import dates


@pytest.fixture
def store(monkeypatch):
    try:
        admin = psycopg.connect(database.DATABASE_URL, connect_timeout=2, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL nicht erreichbar")
    name = "test_follow_up_" + uuid4().hex
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = make_conninfo(database.DATABASE_URL, dbname=name)
    try:
        assert migrate.run_migrations(dsn)["status"] == "ok"
        connect = lambda: psycopg.connect(dsn)
        for module in (database, suggestions, threads):
            monkeypatch.setattr(module, "get_connection", connect)
        vector = [1.0] + [0.0] * 383
        monkeypatch.setattr(threads, "embed_document", lambda _: vector)
        monkeypatch.setattr(threads, "embed_query", lambda _: vector)
        # Berlin is already Nov 7 while UTC is still Nov 6.
        monkeypatch.setattr(dates, "now_berlin", lambda: datetime(2026, 11, 6, 23, 30, tzinfo=timezone.utc).astimezone(dates.BERLIN))
        yield connect
    finally:
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        admin.close()


def advance(monkeypatch, day):
    monkeypatch.setattr(dates, "now_berlin", lambda: datetime(2026, 11, day, 0, 1, tzinfo=dates.BERLIN))


def test_review_waiting_and_resolution(store):
    thread_id = threads.create_thread(
        "Angebot", status="waiting", waiting_for="Antwort vom Handwerker",
        blocked_reason="Angebot fehlt", review_on="2026-11-10", tags=["privat"],
    )
    thread = threads.get_thread(thread_id)
    assert thread["review_on"] == date(2026, 11, 10)
    assert thread["waiting_for"] == "Antwort vom Handwerker"
    assert threads.search_threads("Angebot")[0]["review_on"] == date(2026, 11, 10)
    assert threads.list_threads(review_due_only=True) == []
    assert suggestions.create_suggestion(thread_id, "Nachfragen")["reason"] == "review_not_due"
    unchanged = threads.update_thread(thread_id, next_action="Angebot vergleichen")
    assert unchanged["review_on"] == thread["review_on"]
    updated = threads.update_thread(
        thread_id, status="active", clear_fields=["waiting_for", "blocked_reason", "review_on"],
    )
    assert all(updated[key] is None for key in ("waiting_for", "blocked_reason", "review_on"))
    assert updated["next_action"] == "Angebot vergleichen"
    assert updated["tags"] == ["privat"]
    assert suggestions.create_suggestion(thread_id, "Angebot jetzt vergleichen")["created"]


def test_deferred_suggestion_returns_once_on_berlin_date(store, monkeypatch):
    thread_id = threads.create_thread("Nachfassen", status="waiting")
    sid = suggestions.create_suggestion(thread_id, "Antwort erfragen")["suggestion_id"]
    suggestions.list_suggestions(mark_surfaced=True)
    suggestions.update_suggestion_status(sid, "deferred", deferred_until="2026-11-08")
    assert suggestions.list_suggestions(status="open") == []
    assert threads.list_threads(review_due_only=True) == []
    assert suggestions.create_suggestion(thread_id, "Andere Formulierung")["reason"] == "deferred"
    advance(monkeypatch, 8)
    returned = suggestions.list_suggestions(status="open", delivery="pending")
    assert [s["id"] for s in returned] == [sid]
    assert returned[0]["deferred_until"] is None
    assert suggestions.list_suggestions(status="open", mark_surfaced=True)[0]["delivery_status"] == "surfaced"
    assert suggestions.list_suggestions(delivery="pending") == []
    advance(monkeypatch, 9)
    assert suggestions.list_suggestions(delivery="pending") == []
    assert [t["id"] for t in threads.list_threads(review_due_only=True)] == [thread_id]


def test_review_postponement_and_closed_thread_cleanup(store, monkeypatch):
    tid = threads.create_thread("Projekt", status="waiting", waiting_for="Lieferung")
    sid = suggestions.create_suggestion(tid, "Lieferung prüfen")["suggestion_id"]
    threads.update_thread(tid, review_on="2026-11-09")
    assert suggestions.list_suggestions(status="deferred")[0]["deferred_until"] == date(2026, 11, 9)
    threads.update_thread(tid, review_on="2026-11-12")
    advance(monkeypatch, 9)
    assert suggestions.list_suggestions(status="open") == []
    advance(monkeypatch, 12)
    assert suggestions.list_suggestions(status="open")[0]["id"] == sid
    suggestions.update_suggestion_status(sid, "deferred", deferred_until="2026-11-14")
    closed = threads.update_thread(tid, status="completed")
    assert closed["review_on"] is None and closed["waiting_for"] is None
    assert suggestions.list_suggestions()[0]["status"] == "dismissed"
    advance(monkeypatch, 15)
    assert suggestions.list_suggestions(status="open") == []
    assert suggestions.create_suggestion(tid, "Nochmal nachfragen")["reason"] == "thread_closed"


def test_validation_and_atomicity(store):
    tid = threads.create_thread("Projekt", blocked_reason="Fehlt", review_on="2026-11-10")
    with pytest.raises(ValueError):
        threads.update_thread(tid, review_on="2026-11-11", clear_fields=["review_on"])
    with pytest.raises(ValueError):
        threads.update_thread(tid, clear_fields=["title"])
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        threads.update_thread(tid, clear_fields=["review_on", "blocked_reason"], source_message_id=-1)
    assert threads.get_thread(tid)["blocked_reason"] == "Fehlt"
    assert threads.get_thread(tid)["review_on"] == date(2026, 11, 10)
    sid = suggestions.create_suggestion(None, "Allgemeiner Hinweis")["suggestion_id"]
    for invalid in ("2026-11-06", "2026-11-07", "kein Datum"):
        with pytest.raises(ValueError):
            suggestions.update_suggestion_status(sid, "deferred", deferred_until=invalid)
    with pytest.raises(ValueError):
        suggestions.update_suggestion_status(sid, "confirmed", deferred_until="2026-11-09")
    assert suggestions.list_suggestions()[0]["status"] == "open"
    suggestions.update_suggestion_status(sid, "deferred")
    assert suggestions.list_suggestions(status="open") == []
    assert suggestions.list_suggestions(status="deferred")[0]["deferred_until"] is None


def test_resolved_waiting_retires_old_reminders(store, monkeypatch):
    tid = threads.create_thread("Angebot", status="waiting", waiting_for="Firma", blocked_reason="Angebot fehlt")
    sid = suggestions.create_suggestion(tid, "Angebot erneut anfragen")["suggestion_id"]
    suggestions.update_suggestion_status(sid, "deferred", deferred_until="2026-11-10")
    threads.update_thread(
        tid, status="active", next_action="Angebot vergleichen",
        clear_fields=["waiting_for", "blocked_reason", "review_on"],
    )
    advance(monkeypatch, 11)
    assert suggestions.list_suggestions(status="open") == []
    assert suggestions.list_suggestions()[0]["status"] == "dismissed"
    assert suggestions.create_suggestion(tid, "Angebot vergleichen")["created"]


def test_authenticated_api_and_ui_deferral(store, monkeypatch):
    monkeypatch.setattr(auth, "password_hash", lambda: "configured")
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: True)
    tid = threads.create_thread("Angebot prüfen", waiting_for="Firma", review_on="2026-11-07")
    sid = suggestions.create_suggestion(tid, "Angebot anfragen")["suggestion_id"]
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        assert "Wiedervorlage" in client.get(f"/ui/threads/{tid}").text
        result = client.patch(f"/suggestions/{sid}", json={"status": "deferred", "deferred_until": "2026-11-09"})
        assert result.status_code == 200
        assert result.json()["deferred_until"] == "2026-11-09"
        page = client.get("/ui/heute")
        assert "Zurückgestellt bis 09.11.2026" in page.text
        assert client.get("/suggestions?status=open").json()["suggestions"] == []
        response = client.post(f"/ui/suggestions/{sid}", data={"action": "deferred", "deferred_until": "2026-11-10"}, follow_redirects=False)
        assert response.status_code == 303
        assert client.post(f"/ui/suggestions/{sid}", data={"action": "deferred", "deferred_until": "2026-11-07"}).status_code == 400
        assert client.patch(f"/suggestions/{sid}", json={"status": "deferred", "deferred_until": "2026-11-07"}).status_code == 400
        assert suggestions.list_suggestions()[0]["deferred_until"] == date(2026, 11, 10)


def test_worker_evaluation_reopens_due_without_model_duplicates(store, monkeypatch):
    tid = threads.create_thread("Offen", status="waiting", review_on="2026-11-07")
    sid = suggestions.create_suggestion(tid, "Nachfassen")["suggestion_id"]
    suggestions.update_suggestion_status(sid, "deferred", deferred_until="2026-11-08")
    future = threads.create_thread("Später", review_on="2026-11-20")
    monkeypatch.setattr(evaluation, "list_memories", lambda **_: [])
    payloads = []
    def model_loop(instructions, messages, tools, **kwargs):
        payloads.append(messages[0]["content"])
        # Seeing a paused plan as context must not bypass its notification pause.
        result = assistant.execute_tool("create_suggestion", {
            "thread_id": future, "content": "Vorzeitig nachfassen",
        }, run_id=kwargs["run_id"])
        assert not result["created"]
        return "Keine weiteren Hinweise."
    monkeypatch.setattr(evaluation, "run_tool_loop", model_loop)
    before = evaluation.run_evaluation(trigger="scheduled")
    assert before["threads_considered"] == 2
    advance(monkeypatch, 8)
    after = evaluation.run_evaluation(trigger="scheduled")
    assert after["threads_considered"] == 2
    assert after["suggestions_created"] == 0
    assert '"status": "open"' in payloads[-1]
    assert suggestions.list_suggestions(status="open")[0]["id"] == sid
    assert all(t["id"] != future for t in threads.list_threads(review_due_only=True))


def test_chat_tools_preserve_follow_up_intent(monkeypatch):
    captured = {}
    monkeypatch.setattr(assistant, "create_thread", lambda *a, **kw: captured.update(kw) or 1)
    assistant.execute_tool("create_thread", {"title": "Angebot", "review_on": "2026-11-10", "waiting_for": "Firma"})
    assert captured["review_on"] == "2026-11-10" and captured["waiting_for"] == "Firma"
    monkeypatch.setattr(assistant, "update_thread", lambda *a, **kw: captured.update(kw) or {"id": 1})
    assistant.execute_tool("update_thread", {"thread_id": 1, "clear_fields": ["waiting_for", "blocked_reason"]})
    assert captured["clear_fields"] == ["waiting_for", "blocked_reason"]
    assert assistant.execute_tool("update_thread", {"thread_id": 1, "clear_fields": []})["reason"] == "no_changes"
    monkeypatch.setattr(assistant, "update_suggestion_status", lambda *a, **kw: captured.update(kw) or {"id": a[0]})
    assert assistant.execute_tool("defer_suggestion", {"suggestion_id": 3, "deferred_until": "2026-11-10"})["updated"]
    assert captured["deferred_until"] == "2026-11-10"
    names = {t["name"] for t in evaluation.EVALUATION_TOOLS}
    assert "defer_suggestion" not in names and "update_thread" not in names
    for tool in assistant.TOOLS:
        params = tool["parameters"]
        assert set(params["required"]) == set(params["properties"])
