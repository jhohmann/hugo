"""Typed cards and immutable replies against disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from test_follow_up import store
from app.storage import suggestions, suggestion_responses as replies, threads, thread_events


def card(kind, **kwargs):
    return suggestions.create_suggestion(
        threads.create_thread("Hausmodernisierung"), "Wie ist der Stand?", kind=kind, **kwargs,
    )["suggestion_id"]


def answer(sid, code, **kwargs):
    return replies.answer_suggestion(sid, code, expected_revision=1, **kwargs)


@pytest.mark.parametrize("kind,options,free,tid", [
    ("info", [], False, 1), ("status_check", [], False, None),
    ("proposal", ["Ja"], False, 1), ("proposal", [], True, 1),
    ("question", [], False, 1), ("question", ["x", "x"], False, 1),
    ("question", [{"action": "complete"}], False, 1),
])
def test_invalid_contract_before_io(monkeypatch, kind, options, free, tid):
    monkeypatch.setattr(suggestions, "get_connection", lambda: pytest.fail("Unexpected DB access"))
    with pytest.raises(ValueError):
        suggestions.create_suggestion(tid, "Frage", kind=kind, response_options=options, allow_free_text=free)


def test_old_proposals_survive_migration_and_default_contract(store):
    sid = card("proposal")
    saved = suggestions.list_suggestions()[0]
    assert saved["kind"] == "proposal" and saved["response_options"] == []
    assert not saved["allow_free_text"] and saved["revision"] == 1
    answer(sid, "accepted")
    assert suggestions.list_suggestions()[0]["status"] == "confirmed"
    assert threads.get_thread(saved["thread_id"])["status"] == "proposed"


@pytest.mark.parametrize("code", list(replies.STATUS_ANSWERS))
def test_status_answers_are_durable_user_messages(store, code):
    sid = card("status_check")
    result = answer(sid, code)
    with store() as conn:
        stored = conn.execute("SELECT answer, response_text, source, message_id FROM suggestion_responses").fetchone()
        assert stored[:3] == (code, replies.STATUS_ANSWERS[code], "ui")
        assert conn.execute("SELECT role, content FROM messages WHERE id = %s", (stored[3],)).fetchone() == ("user", replies.STATUS_ANSWERS[code])
        assert conn.execute("SELECT count(*) FROM thread_messages").fetchone()[0] == 2
    if code == "completed":
        thread = threads.list_threads(status="completed")[0]
        with store() as conn:
            assert conn.execute("SELECT origin FROM thread_events WHERE thread_id = %s ORDER BY id DESC LIMIT 1", (thread["id"],)).fetchone()[0] == "user_decision"
    assert result["conversation_id"]


@pytest.mark.parametrize("code,text,expected", [
    ("option:0", "", "Ungefähr zwei Tage"), ("text", "Eher drei Wochen", "Eher drei Wochen"),
])
def test_question_context_and_options(store, code, text, expected):
    sid = card("question", response_options=["Ungefähr zwei Tage"], allow_free_text=True)
    result = answer(sid, code, text=text, source="api")
    with store() as conn:
        assert conn.execute("SELECT response_text, source FROM suggestion_responses").fetchone() == (expected, "api")
        messages = conn.execute("SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY id", (result["conversation_id"],)).fetchall()
        assert messages == [("assistant", "Wie ist der Stand?"), ("user", expected)]


def test_invalid_answer_and_generic_confirm_do_not_mutate(store):
    sid = card("question", allow_free_text=True)
    with pytest.raises(ValueError):
        answer(sid, "completed")
    with pytest.raises(ValueError):
        suggestions.update_suggestion_status(sid, "confirmed")
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestion_responses").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM conversations").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM suggestions").fetchone()[0] == "open"


def test_replay_and_conflicting_reply(store):
    sid = card("status_check")
    first = answer(sid, "in_progress")
    repeated = answer(sid, "in_progress")
    assert repeated["replayed"]
    assert repeated["conversation_id"] == first["conversation_id"]
    with pytest.raises(replies.SuggestionConflict):
        answer(sid, "completed")
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestion_responses").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM conversations").fetchone()[0] == 1


def test_stale_revision_and_closed_thread(store):
    sid = card("status_check")
    suggestions.update_suggestion_status(sid, "deferred")
    with pytest.raises(replies.SuggestionConflict):
        answer(sid, "in_progress")
    tid = suggestions.list_suggestions()[0]["thread_id"]
    threads.update_thread(tid, status="completed")
    with pytest.raises(replies.SuggestionConflict):
        replies.answer_suggestion(sid, "in_progress", expected_revision=3)


def test_concurrent_answers_create_one_response(store):
    sid = card("status_check")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: answer(sid, "in_progress"), range(2)))
    assert sorted(r["replayed"] for r in results) == [False, True]
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestion_responses").fetchone()[0] == 1


def test_completion_failure_rolls_back_reply_and_messages(store, monkeypatch):
    sid = card("status_check")
    def fail(*a, **kw):
        raise RuntimeError("Simulierter Fehler")
    monkeypatch.setattr(threads, "update_thread", fail)
    with pytest.raises(RuntimeError):
        answer(sid, "completed")
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestion_responses").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM suggestions").fetchone()[0] == "open"


def test_pause_is_independent_and_requires_explicit_resume(store):
    tid = threads.create_thread("Wartendes Projekt", status="waiting", waiting_for="Angebot")
    sid = suggestions.create_suggestion(tid, "Stand?", kind="status_check")["suggestion_id"]
    other = suggestions.create_suggestion(tid, "Angebot prüfen")["suggestion_id"]
    answer(sid, "paused")
    state = threads.get_thread(tid)
    assert state["paused"] and state["status"] == "waiting" and state["waiting_for"] == "Angebot"
    assert state["last_response_at"] and state["last_confirmed_at"]
    assert state["last_progress_on"] is None and state["progress_recorded_at"] is None
    assert suggestions.create_suggestion(tid, "Ganz anders formuliert")["reason"] == "thread_paused"
    assert threads.list_threads(review_due_only=True) == []
    assert threads.list_threads(open_only=True)[0]["id"] == tid
    with pytest.raises(ValueError):
        threads.update_thread(tid, paused=False, agent_write=True)
    threads.update_thread(tid, paused=False, user_decision=True)
    assert suggestions.create_suggestion(tid, "Aktuellen Stand klären")["created"]
    assert next(s for s in suggestions.list_suggestions() if s["id"] == other)["status"] == "dismissed"


@pytest.mark.parametrize("code", ["in_progress", "no_progress"])
def test_confirmed_stand_is_not_progress(store, code):
    sid = card("status_check")
    tid = suggestions.list_suggestions()[0]["thread_id"]
    before = threads.get_thread(tid)
    assert before["last_progress_on"] is None and before["last_confirmed_at"] is None
    answer(sid, code)
    state = threads.get_thread(tid)
    assert state["last_confirmed_at"] and state["last_response_at"]
    assert state["last_progress_on"] is None and state["progress_recorded_at"] is None
    assert replies.list_thread_responses(tid)[0]["text"] == replies.STATUS_ANSWERS[code]


def test_hint_question_and_actual_progress_have_distinct_times(store):
    from datetime import date
    tid = threads.create_thread("Projekt")
    state = threads.get_thread(tid)
    assert state["last_hint_at"] is None
    sid = suggestions.create_suggestion(tid, "Wie lange brauchst du?", kind="question", allow_free_text=True)["suggestion_id"]
    assert threads.get_thread(tid)["last_hint_at"] is not None
    answer(sid, "text", text="Zwei Wochen")
    state = threads.get_thread(tid)
    assert state["last_response_at"] and state["last_confirmed_at"] is None
    assert state["last_progress_on"] is None
    context = replies.list_thread_responses(tid)[0]
    with store() as conn:
        evidence = conn.execute("INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', 'Am 5. November habe ich das erste Arbeitspaket fertiggestellt.') RETURNING id", (context["conversation_id"],)).fetchone()[0]
    threads.update_thread(tid, last_progress_on="2026-11-05", source_message_id=evidence, agent_write=True)
    state = threads.get_thread(tid)
    assert state["last_progress_on"] == date(2026, 11, 5) and state["progress_recorded_at"]
    with pytest.raises(ValueError):
        threads.update_thread(tid, last_progress_on="2026-11-04", agent_write=True)
    with pytest.raises(ValueError):
        threads.update_thread(tid, last_progress_on="2099-01-01", source_message_id=evidence, agent_write=True)


def test_same_occasion_survives_rewording_and_user_rejection(store):
    tid = threads.create_thread("Projekt")
    first = suggestions.create_suggestion(tid, "Wie ist der Stand?", kind="status_check", occasion_key="Stand:Offen")
    suggestions.update_suggestion_status(first["suggestion_id"], "dismissed", source="ui")
    repeated = suggestions.create_suggestion(tid, "Gibt es neue Entwicklungen?", kind="question",
                                             allow_free_text=True, occasion_key="stand:offen")
    assert not repeated["created"] and repeated["reason"] == "same_occasion"
    assert repeated["suggestion_id"] == first["suggestion_id"]
    reactions = suggestions.list_recent_reactions(thread_id=tid)
    assert reactions[0]["action"] == "dismissed" and reactions[0]["source"] == "ui"
    assert reactions[0]["occasion_key"] == "stand:offen"


def test_distinct_new_occasion_can_repeat_a_handled_action(store):
    tid = threads.create_thread("Angebote")
    first = suggestions.create_suggestion(tid, "Angebot prüfen", occasion_key="angebot:erstes")
    suggestions.update_suggestion_status(first["suggestion_id"], "dismissed", source="api")
    threads.update_thread(tid, description="Zweites Angebot ist eingetroffen")
    second = suggestions.create_suggestion(tid, "Angebot prüfen", reason="Zweites Angebot ist eingetroffen", occasion_key="angebot:zweites")
    assert second["created"]
    assert len(suggestions.list_suggestions()) == 2


def test_general_occasion_and_legacy_text_are_safe_under_concurrency(store):
    for key in (None, "allgemeiner-anlass"):
        text = "Allgemeine Entscheidung" if key else "Anderer allgemeiner Text"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: suggestions.create_suggestion(None, text, occasion_key=key), range(2)))
        assert sum(r["created"] for r in results) == 1


def test_reactions_are_read_only_and_not_reconstructed_from_internal_changes(store):
    sid = card("proposal")
    tid = suggestions.list_suggestions()[0]["thread_id"]
    suggestions.update_suggestion_status(sid, "deferred", deferred_until="2026-11-10", source="ui")
    suggestions.update_suggestion_status(sid, "deferred", deferred_until="2026-11-10", source="ui")
    events = suggestions.list_recent_reactions(thread_id=tid)
    assert len(events) == 1 and events[0]["deferred_until"].isoformat() == "2026-11-10"
    with store() as conn:
        before = conn.execute("SELECT status, revision, delivery_status FROM suggestions WHERE id = %s", (sid,)).fetchone()
    assert suggestions.list_recent_reactions(thread_id=tid) == events
    with store() as conn:
        assert conn.execute("SELECT status, revision, delivery_status FROM suggestions WHERE id = %s", (sid,)).fetchone() == before
    suggestions.update_suggestion_status(sid, "dismissed")  # internal cleanup is not a user preference
    assert len(suggestions.list_recent_reactions(thread_id=tid)) == 1


def test_two_evaluations_keep_reworded_rejected_occasion_single(store, monkeypatch):
    from app.agent import evaluation, assistant
    tid = threads.create_thread("Langfristiges undatiertes Vorhaben")
    monkeypatch.setattr(evaluation, "list_memories", lambda **kw: [])
    turns = []
    def model(instructions, messages, tools, **kwargs):
        turns.append(messages[0]["content"])
        result = assistant.execute_tool("create_suggestion", {
            "thread_id": tid, "content": "Wie ist der Stand?" if len(turns) == 1 else "Gibt es Neuigkeiten?",
            "kind": "status_check", "occasion_key": "unbekannter-stand", "response_options": [], "allow_free_text": False,
        }, run_id=kwargs["run_id"])
        return "Meldung erstellt." if result["created"] else "Kein neuer Anlass."
    monkeypatch.setattr(evaluation, "run_tool_loop", model)
    first = evaluation._run_evaluation("scheduled")
    assert first["suggestions_created"] == 1
    sid = suggestions.list_suggestions()[0]["id"]
    suggestions.update_suggestion_status(sid, "dismissed", source="ui")
    second = evaluation._run_evaluation("scheduled")
    assert second["suggestions_created"] == 0
    assert '"action": "dismissed"' in turns[1]
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM memories").fetchone()[0] == 0


def test_obsolete_card_is_audited_without_rewriting_user_reaction(store):
    sid = card("question", allow_free_text=True)
    result = suggestions.update_suggestion_status(sid, "dismissed", expected_revision=1,
        source="internal", only_unhandled=True, reaction_reason="Die Aufwandsschätzung liegt inzwischen vor.")
    assert result["status"] == "dismissed"
    assert result["obsolete_reason"] == "Die Aufwandsschätzung liegt inzwischen vor."
    with store() as conn:
        assert conn.execute("SELECT reason, source FROM suggestion_reactions WHERE suggestion_id=%s", (sid,)).fetchone() == ("Die Aufwandsschätzung liegt inzwischen vor.", "internal")
    assert suggestions.list_suggestions()[0]["obsolete_reason"] == "Die Aufwandsschätzung liegt inzwischen vor."
    assert suggestions.list_recent_reactions() == []
    handled = card("status_check")
    answer(handled, "in_progress")
    with pytest.raises(replies.SuggestionConflict):
        suggestions.update_suggestion_status(handled, "dismissed", source="internal", expected_revision=2,
            only_unhandled=True, reaction_reason="Darf nicht umgeschrieben werden.")
    with store() as conn:
        assert conn.execute("SELECT status FROM suggestions WHERE id=%s", (handled,)).fetchone()[0] == "confirmed"


@pytest.mark.parametrize("kind,code,options", [
    ("proposal", "accepted", {}), ("status_check", "in_progress", {}),
    ("question", "option:0", {"response_options": ["Zwei Tage"]}),
])
def test_answer_is_protected_across_legacy_writers(store, kind, code, options):
    sid = card(kind, **options)
    first = answer(sid, code)
    before = suggestions.list_suggestions()[0]
    for source in ("ui", "api", "chat", "internal"):
        for status in ("dismissed", "deferred", "open"):
            with pytest.raises(replies.SuggestionConflict):
                suggestions.update_suggestion_status(sid, status, source=source)
    assert suggestions.list_suggestions()[0] == before
    assert answer(sid, code)["conversation_id"] == first["conversation_id"]
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestion_responses").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM suggestion_reactions").fetchone()[0] == 0


@pytest.mark.parametrize("status,other", [("confirmed", "dismissed"), ("dismissed", "confirmed")])
def test_legacy_terminal_retries_are_read_only(store, status, other):
    sid = card("proposal")
    first = suggestions.update_suggestion_status(sid, status, source="api")
    assert suggestions.update_suggestion_status(sid, status, source="api") == first
    with pytest.raises(replies.SuggestionConflict):
        suggestions.update_suggestion_status(sid, other, source="api")
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestion_reactions").fetchone()[0] == 1


def test_legacy_http_paths_protect_answers_and_honor_revision(store, monkeypatch):
    from fastapi.testclient import TestClient
    from app import auth
    from app.main import app

    monkeypatch.setattr(auth, "password_hash", lambda: "configured")
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: True)
    sid = card("question", allow_free_text=True)
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        assert client.patch(f"/suggestions/{sid}", json={"status": "deferred", "expected_revision": 1}).status_code == 200
        assert client.patch(f"/suggestions/{sid}", json={"status": "dismissed", "expected_revision": 1}).status_code == 409
        assert client.post(f"/suggestions/{sid}/answer", json={
            "answer": "text", "text": "Zwei Tage", "expected_revision": 2,
        }).status_code == 200
        # Compatibility payloads omit revisions but cannot overwrite an answer.
        assert client.patch(f"/suggestions/{sid}", json={"status": "dismissed"}).status_code == 409
        assert client.post(f"/ui/suggestions/{sid}", data={"action": "dismissed"}).status_code == 409
        assert client.patch(f"/suggestions/{sid}", json={"status": "dismissed", "expected_revision": 0}).status_code == 422
    assert suggestions.list_suggestions()[0]["status"] == "confirmed"


def test_answer_racing_with_legacy_dismissal_keeps_one_decision(store):
    sid = card("question", response_options=["Zwei Tage"])
    def write(action):
        try:
            if action == "answer":
                answer(sid, "option:0")
            else:
                suggestions.update_suggestion_status(sid, "dismissed", source="api")
            return action
        except replies.SuggestionConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["answer", "dismiss"]))
    assert results.count("conflict") == 1
    with store() as conn:
        response_count = conn.execute("SELECT count(*) FROM suggestion_responses").fetchone()[0]
        reaction_count = conn.execute("SELECT count(*) FROM suggestion_reactions").fetchone()[0]
        assert response_count + reaction_count == 1
        status = conn.execute("SELECT status FROM suggestions WHERE id = %s", (sid,)).fetchone()[0]
        assert status == ("confirmed" if response_count else "dismissed")
