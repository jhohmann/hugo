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


def test_chatgpt_usage_indicator_and_access_errors(client, fake_storage, monkeypatch):
    from app.agent.model_client import ModelAccessError
    from app.agent import model_usage
    from app import main
    monkeypatch.setenv("HUGO_MODEL_PROVIDER", "chatgpt")
    monkeypatch.setenv("HUGO_API_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(model_usage, "public_status", lambda: {
        "connected": True, "limited": True, "retry_at": None,
        "last": {"route": "api", "model": "gpt-5-mini", "input_tokens": 20, "output_tokens": 3},
    })
    page = client.get("/ui/chat")
    assert "KI-Zugang: API-Reserve" in page.text
    assert "verbleibende Abo-Kontingent ist hier nicht abrufbar" in page.text
    assert "20 Eingabe- / 3 Ausgabetokens" in page.text
    assert "https://chatgpt.com/settings/usage" in page.text
    def unavailable(*_):
        raise ModelAccessError("ChatGPT-Kontingentgrenze erreicht.")
    monkeypatch.setattr(web_routes, "run_chat", unavailable)
    monkeypatch.setattr(main, "run_chat", unavailable)
    response = client.post("/ui/chat", data={"message": "Mein Entwurf"})
    assert response.status_code == 503
    assert "Mein Entwurf" in response.text and "Kontingentgrenze" in response.text
    assert client.post("/chat", json={"message": "Test"}).status_code == 503


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
    def fake_today(*, status="open", page=1, mark_surfaced=False):
        cards = fake_list_suggestions(status=status, mark_surfaced=mark_surfaced)
        groups = {}
        for card in cards:
            key = card["thread_id"] if card["thread_id"] is not None else f"general:{card['id']}"
            group = groups.setdefault(key, {"thread_id": card["thread_id"], "cards": [], "count": 0,
                                           "title": (fake_get_thread(card["thread_id"]) or {}).get("title")})
            group["cards"].append(card)
            group["count"] += 1
        return {"groups": list(groups.values()), "total_count": len(cards), "group_count": len(groups), "page": 1, "page_count": 1}
    monkeypatch.setattr(web_routes, "list_today", fake_today)
    monkeypatch.setattr(web_routes, "count_open_suggestions", lambda: sum(s["status"] == "open" for s in state["suggestions"]))
    monkeypatch.setattr(web_routes, "list_suggestions", fake_list_suggestions)
    monkeypatch.setattr(
        web_routes, "list_runs", lambda limit=50: state["runs"]
    )
    monkeypatch.setattr(
        web_routes, "list_threads",
        lambda limit=50, tag=None: [t for t in state["threads"] if tag is None or tag in t.get("tags", [])],
    )
    monkeypatch.setattr(web_routes, "get_thread", fake_get_thread)

    def fake_update(suggestion_id, status, deferred_until=None, source="ui", **kwargs):
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


def test_evaluate_already_running(client, fake_storage, monkeypatch):
    monkeypatch.setattr(web_routes, "run_evaluation", lambda trigger: {
        "status": "skipped", "reason": "already_running",
    })
    response = client.post("/ui/evaluate")
    assert response.status_code == 409
    assert "Eine Auswertung läuft bereits" in response.text


@pytest.mark.parametrize("action", ["completed", "archived", "deadline"])
def test_thread_decision_is_explicit_and_scoped(client, fake_storage, monkeypatch, action):
    captured = []
    monkeypatch.setattr(web_routes, "update_thread", lambda tid, **kw: captured.append((tid, kw)) or {"id": tid})
    response = client.post("/ui/threads/5/decision", data={
        "action": action, "expected_updated_at": "2026-11-17T10:00:00+00:00",
        "deadline": "2027-03-28", "priority": "5", "agent_write": "false",
    }, follow_redirects=False)
    assert response.status_code == 303
    tid, changes = captured[0]
    assert tid == 5 and changes["user_decision"] is True
    assert "priority" not in changes and "agent_write" not in changes
    if action == "deadline":
        assert changes["deadline"].isoformat() == "2027-03-28T23:59:59.999999+02:00"
    else:
        assert changes["status"] == action


@pytest.mark.parametrize("data", [
    {"action": "active"},
    {"action": "completed", "expected_updated_at": "2026-11-17T10:00:00"},
    {"action": "deadline", "expected_updated_at": "2026-11-17T10:00:00Z", "deadline": ""},
    {"action": "deadline", "expected_updated_at": "2026-11-17T10:00:00Z", "deadline": "morgen"},
])
def test_invalid_thread_decision_has_no_write(client, fake_storage, monkeypatch, data):
    monkeypatch.setattr(web_routes, "update_thread", lambda *a, **kw: pytest.fail("Unexpected write"))
    assert client.post("/ui/threads/5/decision", data=data).status_code == 400


def test_thread_decision_conflict_missing_and_origin(client, fake_storage, monkeypatch):
    data = {"action": "completed", "expected_updated_at": "2026-11-17T10:00:00Z"}
    def conflict(*a, **kw):
        raise web_routes.ThreadConflict("Bitte neu laden.")
    monkeypatch.setattr(web_routes, "update_thread", conflict)
    assert client.post("/ui/threads/5/decision", data=data).status_code == 409
    monkeypatch.setattr(web_routes, "update_thread", lambda *a, **kw: None)
    assert client.post("/ui/threads/999/decision", data=data).status_code == 404
    assert client.post("/ui/threads/5/decision", data=data, headers={"Origin": "https://elsewhere.test"}).status_code == 403


def test_thread_decision_form_preserves_precise_deadline_until_submitted(client, fake_storage):
    page = client.get("/ui/threads/5").text
    assert 'id="entscheidung"' in page
    assert 'name="expected_updated_at"' in page
    assert 'value="2027-03-01"' in page
    assert fake_storage["threads"][0]["deadline"] == datetime(2027, 3, 1, tzinfo=timezone.utc)


def test_typed_cards_have_matching_actions(client, fake_storage):
    base = fake_storage["suggestions"][0]
    fake_storage["suggestions"] = [
        {**base, "id": 51, "kind": "status_check", "revision": 3},
        {**base, "id": 52, "kind": "question", "revision": 1,
         "response_options": ["Zwei Tage", "<script>"], "allow_free_text": True},
    ]
    page = client.get("/ui/heute").text
    assert "Statusabfrage" in page and "Rückfrage" in page
    for label in ("Bin dran", "Pausiert", "Erledigt", "Kein Fortschritt", "Zwei Tage", "Deine Antwort"):
        assert label in page
    assert "&lt;script&gt;" in page
    assert "Bestätigen</button>" not in page
    assert 'name="answer" value="option:1"' in page


def test_typed_answer_ui_and_api_errors(client, fake_storage, monkeypatch):
    from app import main
    from app.storage.suggestion_responses import SuggestionConflict
    calls = []
    def reply(sid, answer, **kwargs):
        calls.append((sid, answer, kwargs))
        return {"answered": True, "replayed": False}
    monkeypatch.setattr(web_routes, "answer_suggestion", reply)
    monkeypatch.setattr(main, "answer_suggestion", reply)
    data = {"answer": "text", "text": "Zwei Wochen", "expected_revision": 2}
    assert client.post("/ui/suggestions/7/answer", data=data, follow_redirects=False).status_code == 303
    assert calls[-1] == (7, "text", {"expected_revision": 2, "text": "Zwei Wochen", "source": "ui"})
    assert client.post("/suggestions/7/answer", json=data).json()["answered"]
    assert calls[-1][2]["source"] == "api"
    def conflict(*a, **kw):
        raise SuggestionConflict("Nicht mehr aktuell")
    monkeypatch.setattr(web_routes, "answer_suggestion", conflict)
    monkeypatch.setattr(main, "answer_suggestion", conflict)
    assert client.post("/ui/suggestions/7/answer", data=data).status_code == 409
    assert client.post("/suggestions/7/answer", json=data).status_code == 409
    assert client.post("/suggestions/7/answer", json={"answer": "text"}).status_code == 422


def test_explicit_resume_and_paused_details(client, fake_storage, monkeypatch):
    thread = fake_storage["threads"][0]
    thread["paused"] = True
    page = client.get("/ui/threads/5").text
    assert "Pausiert – keine neuen Hinweise" in page and "Vorhaben fortsetzen" in page
    seen = []
    monkeypatch.setattr(web_routes, "update_thread", lambda tid, **kw: seen.append(kw) or {"id": tid})
    result = client.post("/ui/threads/5/decision", data={"action": "resume", "expected_updated_at": "2026-11-17T10:00:00Z"}, follow_redirects=False)
    assert result.status_code == 303
    assert seen[0]["paused"] is False and seen[0]["user_decision"] is True


def test_today_groups_one_project_and_shows_total(client, fake_storage):
    base = fake_storage["suggestions"][0]
    fake_storage["suggestions"] = [base, {**base, "id": 99, "content": "Weitere Entscheidung"}]
    page = client.get("/ui/heute").text
    assert "2 offene Meldungen" in page and "2 Meldungen" in page
    assert page.count('class="today-group"') == 1
    assert 'name="next" value="/ui/heute?page=1&amp;deferred_page=1"' in page


def test_navigation_counts_without_loading_cards(client, fake_storage):
    base = fake_storage["suggestions"][0]
    fake_storage["suggestions"] = [{**base, "id": i} for i in range(503)]
    fake_storage["surfaced_calls"].clear()
    page = client.get("/ui/threads").text
    assert '>503</span>' in page
    assert fake_storage["surfaced_calls"] == []


def test_today_pagination_validation(client, fake_storage):
    assert client.get("/ui/heute?page=0").status_code == 422
    assert client.get("/ui/heute?deferred_page=-1").status_code == 422
