"""Tests für die Weboberfläche (MVP 0.1).

Laufen ohne Datenbank und ohne OpenAI-Zugriff:
Storage-, Agenten- und Evaluationsfunktionen werden
im Web-Modul ersetzt (monkeypatch).
"""

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import formatting as fmt
from app.web import routes as web_routes
from app import chat_service
from app import auth


@pytest.fixture
def client(monkeypatch):
    # These tests exercise authenticated UI behavior; login itself has separate tests.
    monkeypatch.setattr(auth, "password_hash", lambda: "test-configured")
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: True)
    return TestClient(app, headers={"Origin": "http://testserver"})


def test_thread_area_filter_and_detail(client, fake_storage):
    fake_storage["threads"][0]["tags"] = ["privat"]
    fake_storage["threads"][1]["tags"] = ["arbeit", "privat"]
    response = client.get("/ui/threads?tag=arbeit")
    assert response.status_code == 200
    assert "Schottland" in response.text and "Norwegen-Reise" not in response.text
    assert 'value="arbeit" selected' in response.text
    detail = client.get("/ui/threads/6")
    assert "Arbeit, Privat" in detail.text
    assert "Norwegen-Reise" in client.get("/ui/threads?tag=").text
    assert client.get("/ui/threads?tag=unknown").status_code == 400


def test_reference_badges_picker_and_thread_chat(client, fake_storage, monkeypatch):
    monkeypatch.setattr(web_routes, "conversation_threads", lambda ids: {7: [{"id": 5, "title": "Norwegen-Reise"}]})
    monkeypatch.setattr(web_routes, "thread_conversations", lambda tid, page=1: {
        "items": [{"id": 7, "preview": "Frage <script>bad()</script>",
                   "last_linked": datetime(2026, 11, 9), "has_older": True,
                   "messages": [{"role": "assistant", "content": "Antwort <script>bad()</script>"}]}],
        "page": page, "has_more": True,
    })
    chat = client.get("/ui/chat/7").text
    assert 'class="thread-code"' in chat and "V-5" in chat
    assert 'href="/ui/threads/5"' in chat and 'id="chat-thread"' in chat
    new = client.get("/ui/chat?thread_id=5")
    assert new.status_code == 200 and "V-5: " in new.text
    assert client.get("/ui/chat?thread_id=999").status_code == 404
    detail = client.get("/ui/threads/5").text
    assert "V-5" in detail and "Gespräche zu diesem Vorhaben" in detail
    assert 'href="/ui/chat/7"' in detail and "Die letzten 12 Nachrichten" in detail
    assert '&lt;script&gt;' in detail and '<script>bad()</script>' not in detail
    assert "?chat_page=2#gespraeche" in detail
    assert client.get("/ui/threads/5?chat_page=0").status_code == 422


def test_reference_selection_without_javascript_and_errors(client, fake_storage, monkeypatch):
    seen = []
    monkeypatch.setattr(web_routes, "run_chat", lambda message, cid: seen.append(message) or {"conversation_id": 7})
    response = client.post("/ui/chat", data={"message": "Was fehlt?", "thread_id": "5"}, follow_redirects=False)
    assert response.status_code == 303 and seen == ["V-5: Was fehlt?"]
    client.post("/ui/chat", data={"message": "V-5: Was fehlt?", "thread_id": "5"})
    assert seen[-1] == "V-5: Was fehlt?"
    from app.tools.thread_references import ThreadReferenceError
    def missing(*_):
        raise ThreadReferenceError("Vorhaben V-999 wurde nicht gefunden.")
    monkeypatch.setattr(web_routes, "run_chat", missing)
    error = client.post("/ui/chat", data={"message": "V-999: Entwurf"})
    assert error.status_code == 400 and "V-999: Entwurf" in error.text
    from app import main
    monkeypatch.setattr(main, "run_chat", missing)
    assert client.post("/chat", json={"message": "V-999"}).status_code == 400


def test_thread_api_area_filter(client, monkeypatch):
    from app import main
    calls = []
    monkeypatch.setattr(main, "list_threads", lambda **kwargs: calls.append(kwargs) or [{"id": 1, "tags": ["arbeit"]}])
    response = client.get("/threads?tag=arbeit&status=active")
    assert response.status_code == 200
    assert response.json()["threads"][0]["tags"] == ["arbeit"]
    assert calls == [{"status": "active", "limit": 100, "tag": "arbeit"}]
    assert client.get("/threads?tag=unknown").status_code == 400
    assert len(calls) == 1


@pytest.fixture
def fake_storage(monkeypatch):
    """Ersetzt alle Datenzugriffe des Web-Moduls."""
    monkeypatch.setattr(web_routes, "conversation_threads", lambda ids: {})
    monkeypatch.setattr(web_routes, "thread_conversations", lambda tid, page=1: {"items": [], "page": page, "has_more": False})
    state = {
        "conversations": [
            {
                "id": 7,
                "created_at": datetime(2026, 11, 1, 10, 0),
                "message_count": 4,
                "last_activity": datetime(2026, 11, 2, 18, 30),
                "preview": "Norwegen im März?",
            }
        ],
        "messages": {
            7: [
                {"role": "user", "content": "Hallo Hugo"},
                {"role": "assistant", "content": "Hallo! Wie kann ich helfen?"},
            ]
        },
        "threads": [
            {
                "id": 5,
                "title": "Norwegen-Reise",
                "description": "Roadtrip entlang der Küste",
                "status": "active",
                "priority": 4,
                "deadline": datetime(2027, 3, 1, tzinfo=timezone.utc),
                "event_start": date(2027, 3, 15),
                "event_end": date(2027, 3, 29),
                "time_precision": "exact",
                "act_by": date(2026, 11, 20),
                "time_text": None,
                "next_action": "Fähre buchen",
                "created_at": datetime(2026, 11, 1, 9, 0),
                "updated_at": datetime(2026, 11, 2, 9, 0),
            },
            {
                "id": 6,
                "title": "Schottland",
                "description": None,
                "status": "proposed",
                "priority": None,
                "deadline": None,
                "event_start": date(2027, 8, 10),
                "event_end": date(2027, 8, 20),
                "time_precision": "approximate",
                "act_by": None,
                "time_text": "Mitte August",
                "next_action": None,
                "created_at": datetime(2026, 11, 1, 9, 0),
                "updated_at": datetime(2026, 11, 1, 9, 0),
            },
        ],
        "suggestions": [
            {
                "id": 11,
                "thread_id": 5,
                "run_id": 3,
                "content": "Fähre für die Norwegen-Reise buchen",
                "reason": "Beliebte Termine sind schnell ausgebucht.",
                "priority": 4,
                "suggested_date": date(2026, 11, 20),
                "delivery_status": "pending",
                "status": "open",
                "created_at": datetime(2026, 11, 3, 6, 0),
                "updated_at": datetime(2026, 11, 3, 6, 0),
            },
            {
                "id": 12,
                "thread_id": None,
                "run_id": 3,
                "content": "Werkstatt-Termin vereinbaren",
                "reason": None,
                "priority": 2,
                "suggested_date": None,
                "delivery_status": "surfaced",
                "status": "deferred",
                "created_at": datetime(2026, 11, 3, 6, 0),
                "updated_at": datetime(2026, 11, 3, 6, 0),
            },
        ],
        "runs": [
            {
                "id": 3,
                "trigger_source": "manual",
                "status": "completed",
                "threads_considered": 2,
                "suggestions_created": 2,
                "error": None,
                "started_at": datetime(2026, 11, 3, 6, 0),
                "finished_at": datetime(2026, 11, 3, 6, 1),
            }
        ],
        "surfaced_calls": [],
        "status_updates": [],
    }

    def fake_list_suggestions(
        status=None, delivery=None, limit=100, mark_surfaced=False
    ):
        state["surfaced_calls"].append(mark_surfaced)
        result = state["suggestions"]
        if status is not None:
            result = [s for s in result if s["status"] == status]
        return result

    def fake_get_thread(thread_id):
        for t in state["threads"]:
            if t["id"] == thread_id:
                return t
        return None

    monkeypatch.setattr(
        web_routes, "list_conversations",
        lambda limit=50: state["conversations"],
    )
    monkeypatch.setattr(
        web_routes, "get_messages",
        lambda cid: state["messages"].get(cid, []),
    )
    monkeypatch.setattr(web_routes, "list_suggestions", fake_list_suggestions)
    monkeypatch.setattr(
        web_routes, "list_runs", lambda limit=50: state["runs"]
    )
    monkeypatch.setattr(
        web_routes, "list_threads",
        lambda limit=50, tag=None: [t for t in state["threads"] if tag is None or tag in t.get("tags", [])],
    )
    monkeypatch.setattr(web_routes, "get_thread", fake_get_thread)

    def fake_update(suggestion_id, status, deferred_until=None):
        state["status_updates"].append((suggestion_id, status))
        for s in state["suggestions"]:
            if s["id"] == suggestion_id:
                s["status"] = status
                return s
        return None

    monkeypatch.setattr(
        web_routes, "update_suggestion_status", fake_update
    )
    monkeypatch.setattr(
        web_routes, "count_pending_actions", lambda: 0
    )
    return state


# --- Formatierung ---


def test_de_date_formats_german():
    assert fmt.de_date(date(2027, 3, 15)) == "15.03.2027"
    assert fmt.de_date(None) == "—"
    assert fmt.de_date("2027-03-15") == "15.03.2027"


def test_relative_label():
    today = date(2026, 11, 3)
    assert fmt.relative_label(date(2026, 11, 3), today) == "heute"
    assert fmt.relative_label(date(2026, 11, 4), today) == "morgen"
    assert fmt.relative_label(date(2026, 11, 8), today) == "in 5 Tagen"
    assert fmt.relative_label(date(2026, 11, 2), today) == "seit gestern"
    assert fmt.relative_label(date(2026, 10, 30), today) == "seit 4 Tagen"
    assert fmt.relative_label(None, today) == ""


def test_urgency_class():
    today = date(2026, 11, 3)
    assert fmt.urgency_class(date(2026, 11, 1), today) == "overdue"
    assert fmt.urgency_class(date(2026, 11, 3), today) == "soon"
    assert fmt.urgency_class(date(2026, 11, 9), today) == "upcoming"
    assert fmt.urgency_class(date(2027, 3, 15), today) == ""
    assert fmt.urgency_class(None, today) == ""


def test_event_range_text():
    assert fmt.event_range_text({
        "event_start": date(2027, 3, 15),
        "event_end": date(2027, 3, 29),
        "time_precision": "exact",
    }) == "15.03.2027 – 29.03.2027"
    assert fmt.event_range_text({
        "event_start": date(2027, 8, 10),
        "event_end": date(2027, 8, 20),
        "time_precision": "approximate",
        "time_text": "Mitte August",
    }) == "ca. 10.08.2027 – 20.08.2027 („Mitte August“)"
    assert fmt.event_range_text({"event_start": None}) == ""


# --- Navigation und Start ---


def test_ui_root_redirects_to_heute(client, fake_storage):
    response = client.get("/ui/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/heute"


def test_navigation_on_all_pages(client, fake_storage):
    for path in ("/ui/chat", "/ui/heute", "/ui/threads"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'href="/ui/chat"' in response.text
        assert 'href="/ui/heute"' in response.text
        assert 'href="/ui/threads"' in response.text
        # Zähler offener Vorschläge in der Navigation
        assert '<span class="badge"' in response.text


# --- Chat ---


def test_chat_new_shows_conversations(client, fake_storage):
    response = client.get("/ui/chat")
    assert response.status_code == 200
    assert "Norwegen im März?" in response.text
    assert 'action="/ui/chat"' in response.text


def test_chat_show_renders_history(client, fake_storage):
    response = client.get("/ui/chat/7")
    assert response.status_code == 200
    assert "Hallo Hugo" in response.text
    assert "Hallo! Wie kann ich helfen?" in response.text
    assert 'value="7"' in response.text


def test_chat_show_unknown_conversation(client, fake_storage):
    response = client.get("/ui/chat/999")
    assert response.status_code == 404
    assert "nicht gefunden" in response.text


def test_sources_are_clickable_in_saved_chat_and_suggestions(client, fake_storage):
    linked = 'Termin. [Veranstalter](https://example.org/race) <script>bad()</script>'
    fake_storage["messages"][7][1]["content"] = linked
    fake_storage["suggestions"][0]["content"] = linked
    fake_storage["suggestions"][0]["reason"] = linked
    fake_storage["threads"][0]["description"] = linked
    for path in ("/ui/chat/7", "/ui/heute", "/ui/threads/5"):
        result = client.get(path)
        assert result.status_code == 200
        assert 'href="https://example.org/race"' in result.text
        assert '<script>bad()</script>' not in result.text
        assert '&lt;script&gt;bad()&lt;/script&gt;' in result.text


def test_chat_send_redirects_to_conversation(
    client, fake_storage, monkeypatch
):
    monkeypatch.setattr(
        web_routes,
        "run_chat",
        lambda message, cid: {"conversation_id": 7, "answer": "Antwort"},
    )
    response = client.post(
        "/ui/chat", data={"message": "Hallo"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/chat/7"


def test_chat_send_empty_message(client, fake_storage):
    response = client.post("/ui/chat", data={"message": "  "})
    assert response.status_code == 400
    assert "Bitte eine Nachricht eingeben" in response.text


def test_chat_send_invalid_conversation_id(client, fake_storage):
    response = client.post(
        "/ui/chat", data={"message": "Hallo", "conversation_id": "abc"}
    )
    assert response.status_code == 400


def test_chat_send_unknown_conversation(
    client, fake_storage, monkeypatch
):
    def fake_run_chat(message, cid):
        raise chat_service.ConversationNotFoundError("unbekannt")

    monkeypatch.setattr(web_routes, "run_chat", fake_run_chat)
    response = client.post(
        "/ui/chat", data={"message": "Hallo", "conversation_id": "999"}
    )
    assert response.status_code == 404


def test_chat_send_agent_failure_keeps_draft(
    client, fake_storage, monkeypatch
):
    def fake_run_chat(message, cid):
        raise RuntimeError("OpenAI nicht erreichbar")

    monkeypatch.setattr(web_routes, "run_chat", fake_run_chat)
    response = client.post(
        "/ui/chat", data={"message": "Mein Entwurf", "conversation_id": "7"}
    )
    assert response.status_code == 502
    assert "konnte gerade nicht antworten" in response.text
    assert "Mein Entwurf" in response.text
    # Verlauf der Unterhaltung bleibt sichtbar
    assert "Hallo Hugo" in response.text


# --- Heute ---


def test_heute_shows_open_and_deferred(client, fake_storage):
    response = client.get("/ui/heute")
    assert response.status_code == 200
    # Offener Vorschlag mit Priorität, Thread-Bezug und Datum
    assert "Fähre für die Norwegen-Reise buchen" in response.text
    assert "prio-4" in response.text
    assert 'href="/ui/threads/5"' in response.text
    assert "Norwegen-Reise" in response.text
    assert "20.11.2026" in response.text
    # Zurückgestellter Vorschlag im eigenen Abschnitt
    assert "Zurückgestellt (1)" in response.text
    assert "Werkstatt-Termin vereinbaren" in response.text
    # Aktionen vorhanden
    assert "Bestätigen" in response.text
    assert "Zurückstellen" in response.text
    assert "Verwerfen" in response.text
    # Letzter Evaluationslauf wird angezeigt
    assert "Letzte Auswertung" in response.text


def test_heute_marks_open_suggestions_surfaced(client, fake_storage):
    client.get("/ui/heute")
    # list_suggestions(status="open", mark_surfaced=True) aufgerufen
    assert True in fake_storage["surfaced_calls"]


def test_heute_empty_state(client, fake_storage):
    fake_storage["suggestions"] = []
    response = client.get("/ui/heute")
    assert response.status_code == 200
    assert "Keine offenen Vorschläge" in response.text


def test_suggestion_action_confirm(client, fake_storage):
    response = client.post(
        "/ui/suggestions/11",
        data={"action": "confirmed"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/heute"
    assert fake_storage["status_updates"] == [(11, "confirmed")]


def test_suggestion_action_respects_safe_next(client, fake_storage):
    response = client.post(
        "/ui/suggestions/11",
        data={"action": "deferred", "next": "/ui/threads/5"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/ui/threads/5"

    response = client.post(
        "/ui/suggestions/11",
        data={"action": "deferred", "next": "https://evil.example"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/ui/heute"


def test_suggestion_action_invalid(client, fake_storage):
    response = client.post(
        "/ui/suggestions/11", data={"action": "open"}
    )
    assert response.status_code == 400
    assert fake_storage["status_updates"] == []


def test_suggestion_action_not_found(client, fake_storage):
    response = client.post(
        "/ui/suggestions/999", data={"action": "confirmed"}
    )
    assert response.status_code == 404


def test_evaluate_trigger(client, fake_storage, monkeypatch):
    calls = []
    monkeypatch.setattr(
        web_routes,
        "run_evaluation",
        lambda trigger: calls.append(trigger) or {"run_id": 4},
    )
    response = client.post("/ui/evaluate", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/heute"
    assert calls == ["manual"]


def test_evaluate_failure(client, fake_storage, monkeypatch):
    def failing(trigger):
        raise RuntimeError("LLM nicht erreichbar")

    monkeypatch.setattr(web_routes, "run_evaluation", failing)
    response = client.post("/ui/evaluate")
    assert response.status_code == 502
    assert "Auswertung ist fehlgeschlagen" in response.text


# --- Vorhaben ---


def test_threads_grouped_by_status(client, fake_storage):
    response = client.get("/ui/threads")
    assert response.status_code == 200
    assert "Aktiv" in response.text
    assert "Idee" in response.text
    assert "Norwegen-Reise" in response.text
    assert "Schottland" in response.text
    # Nächste Aktion und Zeitangaben sichtbar
    assert "Fähre buchen" in response.text
    assert "15.03.2027" in response.text
    assert "handeln bis 20.11.2026" in response.text
    assert "Deadline 01.03.2027" in response.text
    # Ungefähre Angabe mit Originaltext
    assert "Mitte August" in response.text


def test_thread_detail(client, fake_storage):
    response = client.get("/ui/threads/5")
    assert response.status_code == 200
    assert "Norwegen-Reise" in response.text
    assert "Roadtrip entlang der Küste" in response.text
    assert "Fähre buchen" in response.text
    assert "15.03.2027 – 29.03.2027" in response.text
    # Zugehöriger Vorschlag mit Aktionen und Rücksprungziel
    assert "Fähre für die Norwegen-Reise buchen" in response.text
    assert 'value="/ui/threads/5"' in response.text


def test_thread_detail_not_found(client, fake_storage):
    response = client.get("/ui/threads/999")
    assert response.status_code == 404
    assert "nicht gefunden" in response.text


# --- JSON-API bleibt unverändert ---


def test_api_chat_delegates_to_service(monkeypatch, client):
    import app.main as main_module

    calls = []

    def fake_run_chat(message, conversation_id):
        calls.append((message, conversation_id))
        return {"conversation_id": 3, "answer": "Antwort"}

    monkeypatch.setattr(main_module, "run_chat", fake_run_chat)
    response = client.post("/chat", json={"message": "Hallo"})
    assert response.status_code == 200
    assert response.json() == {"conversation_id": 3, "answer": "Antwort"}
    assert calls == [("Hallo", None)]


def test_api_chat_unknown_conversation(monkeypatch, client):
    import app.main as main_module

    def fake_run_chat(message, conversation_id):
        raise chat_service.ConversationNotFoundError("unbekannt")

    monkeypatch.setattr(main_module, "run_chat", fake_run_chat)
    response = client.post(
        "/chat", json={"message": "Hallo", "conversation_id": 999}
    )
    assert response.status_code == 404


def test_api_conversations(monkeypatch, client):
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "list_conversations",
        lambda limit=50: [{"id": 1, "preview": "Hallo"}],
    )
    response = client.get("/conversations")
    assert response.status_code == 200
    assert response.json() == {
        "conversations": [{"id": 1, "preview": "Hallo"}]
    }
