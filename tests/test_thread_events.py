"""Event persistence in disposable PostgreSQL databases, without model calls."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.storage import thread_events, threads
from test_follow_up import store  # Reuse the isolated database fixture.


@pytest.fixture
def history(store, monkeypatch):
    monkeypatch.setattr(thread_events, "get_connection", store)
    return thread_events.list_thread_events


def test_create_update_and_source(history, store):
    with store() as conn:
        cid = conn.execute("INSERT INTO conversations DEFAULT VALUES RETURNING id").fetchone()[0]
        mid = conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', 'Warte auf Angebot') RETURNING id",
            (cid,),
        ).fetchone()[0]
    tid = threads.create_thread("Angebot", source_message_id=mid, tags=["privat"])
    threads.update_thread(tid, status="waiting", waiting_for="Anbieter", source_message_id=mid)
    events = history(tid)
    assert [e["kind"] for e in events] == ["created", "updated"]
    assert all(e["source_message_id"] == mid and e["origin"] == "conversation" for e in events)
    assert events[0]["changes"]["title"] == {"before": None, "after": "Angebot"}
    assert events[1]["changes"] == {
        "status": {"before": "proposed", "after": "waiting"},
        "waiting_for": {"before": None, "after": "Anbieter"},
    }
    assert events[0]["recorded_at"].tzinfo is not None


def test_noop_technical_changes_and_tag_order(history, store):
    tid = threads.create_thread("Projekt", tags=["privat", "arbeit"])
    threads.update_thread(tid, title="Projekt", tags=["privat", "arbeit", "arbeit"])
    with store() as conn:
        conn.execute("UPDATE threads SET embedding = NULL WHERE id = %s", (tid,))
    assert len(history(tid)) == 1
    threads.update_thread(tid, tags=[])
    assert history(tid)[1]["changes"] == {"tags": {"before": ["arbeit", "privat"], "after": []}}


def test_dates_clearing_and_automatic_cleanup(history):
    tid = threads.create_thread(
        "Projekt", status="waiting", waiting_for="Firma", blocked_reason="Angebot",
        review_on="2026-11-12", deadline="2026-12-01T12:00:00+01:00",
    )
    created = history(tid)[0]
    assert created["changes"]["review_on"]["after"] == "2026-11-12"
    assert created["changes"]["deadline"]["after"] == "2026-12-01T11:00:00+00:00"
    threads.update_thread(tid, clear_fields=["blocked_reason"])
    assert history(tid)[1]["changes"] == {"blocked_reason": {"before": "Angebot", "after": None}}
    threads.update_thread(tid, status="completed")
    closed = history(tid)[2]
    assert closed["origin"] == "internal"
    assert closed["automatic_fields"] == ["review_on", "waiting_for"]
    assert closed["changes"]["waiting_for"] == {"before": "Firma", "after": None}
    threads.update_thread(tid, status="completed")
    assert len(history(tid)) == 3


def test_event_failure_rolls_back_thread_and_event(history, store, monkeypatch):
    tid = threads.create_thread("Projekt", tags=["privat"])
    original = threads.record_thread_event

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Simulierter Fehler nach Ereignisspeicherung")

    monkeypatch.setattr(threads, "record_thread_event", fail_after_insert)
    with pytest.raises(RuntimeError):
        threads.update_thread(tid, status="completed", tags=["arbeit"])
    assert threads.get_thread(tid)["status"] == "proposed"
    assert threads.get_thread(tid)["tags"] == ["privat"]
    assert len(history(tid)) == 1
    with pytest.raises(RuntimeError):
        threads.create_thread("Rollback")
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM threads").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM thread_events").fetchone()[0] == 1


def test_concurrent_changes_have_correct_previous_values(history):
    tid = threads.create_thread("Projekt", next_action="Start")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda value: threads.update_thread(tid, next_action=value), ["A", "B"]))
    events = history(tid)
    assert len(events) == 3
    first, second = [event["changes"]["next_action"] for event in events[1:]]
    assert first["before"] == "Start"
    assert second["before"] == first["after"]
    assert second["after"] == threads.get_thread(tid)["next_action"]


def test_pagination_and_isolation(history):
    one = threads.create_thread("Eins")
    two = threads.create_thread("Zwei")
    threads.update_thread(one, priority=5)
    first = history(one, limit=1)
    second = history(one, after_id=first[0]["id"], limit=1)
    assert second[0]["kind"] == "updated"
    assert history(one, after_id=second[0]["id"]) == []
    assert len(history(two)) == 1
    assert threads.update_thread(999999, status="active") is None
    assert history(999999) == []


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"after_id": -1}, {"limit": True}])
def test_invalid_read_parameters(kwargs):
    with pytest.raises(ValueError):
        thread_events.list_thread_events(1, **kwargs)


def test_filtered_pages_and_read_only_dispatch(history, store):
    from app.agent import assistant

    tid = threads.create_thread("Projekt")
    threads.update_thread(tid, status="waiting")
    threads.update_thread(tid, waiting_for="Firma")
    events = history(tid)
    with store() as conn:
        for event, stamp in zip(events, (
            "2026-11-06T22:59:59Z", "2026-11-06T23:00:00Z", "2026-11-07T23:00:00Z",
        )):
            conn.execute("UPDATE thread_events SET recorded_at = %s WHERE id = %s", (stamp, event["id"]))
        before = conn.execute("SELECT to_jsonb(e) FROM thread_events e ORDER BY id").fetchall()
    arguments = {
        "thread_id": tid, "since": "2026-11-07T00:00:00+01:00",
        "until": "2026-11-09T00:00:00+01:00", "limit": 1, "after_id": None,
    }
    first = assistant.execute_tool("list_thread_events", arguments, source_message_id=999999)
    assert first["found"] and first["has_more"]
    assert first["events"][0]["id"] == events[1]["id"]
    second = assistant.execute_tool("list_thread_events", {**arguments, "after_id": first["next_after_id"]})
    assert second["events"][0]["id"] == events[2]["id"]
    assert not second["has_more"] and second["next_after_id"] is None
    one_day = assistant.execute_tool("list_thread_events", {**arguments, "until": "2026-11-08T00:00:00+01:00"})
    assert len(one_day["events"]) == 1 and not one_day["has_more"]
    empty = assistant.execute_tool("list_thread_events", {**arguments, "since": "2026-11-08T12:00:00+01:00"})
    assert empty["found"] and empty["events"] == []
    assert "keine Untätigkeit" in empty["history_note"]
    assert not assistant.execute_tool("list_thread_events", {**arguments, "thread_id": 999999})["found"]
    with store() as conn:
        assert conn.execute("SELECT to_jsonb(e) FROM thread_events e ORDER BY id").fetchall() == before
    assert threads.get_thread(tid)["waiting_for"] == "Firma"


@pytest.mark.parametrize("kwargs", [
    {"since": "2026-11-07"}, {"until": "2026-11-07T12:00:00"},
    {"since": "ungültig"}, {"since": 123},
    {"since": "2026-11-08T00:00:00Z", "until": "2026-11-07T00:00:00Z"},
    {"since": "2026-11-07T00:00:00Z", "until": "2026-11-07T01:00:00+01:00"},
])
def test_invalid_time_filters(kwargs):
    with pytest.raises(ValueError):
        thread_events.list_thread_events_page(1, **kwargs)
