"""Grouped Today pages against disposable PostgreSQL, without model calls."""

from datetime import date

import pytest

from test_follow_up import store
from app.storage import suggestions, threads, today


def test_thread_bundle_keeps_types_and_general_cards_independent(store):
    tid = threads.create_thread("Hausprojekt")
    proposal = suggestions.create_suggestion(tid, "Zeitfenster prüfen")
    status = suggestions.create_suggestion(tid, "Wie ist der Stand?", kind="status_check")
    question = suggestions.create_suggestion(tid, "Wie viel Aufwand?", kind="question", allow_free_text=True)
    suggestions.create_suggestion(None, "Allgemeine Entscheidung eins")
    suggestions.create_suggestion(None, "Allgemeine Entscheidung zwei")
    result = today.list_today()
    assert result["total_count"] == 5 and result["group_count"] == 3
    group = next(g for g in result["groups"] if g["thread_id"] == tid)
    assert group["title"] == "Hausprojekt" and group["count"] == 3
    assert {card["kind"] for card in group["cards"]} == {"proposal", "status_check", "question"}
    assert {card["id"] for card in group["cards"]} == {proposal["suggestion_id"], status["suggestion_id"], question["suggestion_id"]}
    assert len([g for g in result["groups"] if g["thread_id"] is None]) == 2


def test_only_displayed_page_is_surfaced_and_all_groups_remain_reachable(store):
    ids = [threads.create_thread(f"Projekt {i}") for i in range(13)]
    for tid in ids:
        suggestions.create_suggestion(tid, f"Stand von {tid}?", kind="status_check")
    first = today.list_today(groups_per_page=10, mark_surfaced=True)
    assert first["total_count"] == 13 and first["page_count"] == 2
    assert len(first["groups"]) == 10
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestions WHERE delivery_status='surfaced'").fetchone()[0] == 10
        assert conn.execute("SELECT count(*) FROM suggestions WHERE delivery_status='pending'").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM threads WHERE last_progress_on IS NOT NULL OR last_response_at IS NOT NULL OR last_confirmed_at IS NOT NULL").fetchone()[0] == 0
    second = today.list_today(page=2, groups_per_page=10, mark_surfaced=True)
    assert {g["thread_id"] for g in first["groups"]} | {g["thread_id"] for g in second["groups"]} == set(ids)
    assert not ({g["thread_id"] for g in first["groups"]} & {g["thread_id"] for g in second["groups"]})
    assert today.list_today(page=99, groups_per_page=10)["page"] == 2


def test_order_uses_existing_model_priority_and_recommended_date(store):
    ids = [threads.create_thread(name) for name in ("Ohne Datum", "Mit Datum", "Höchste Priorität")]
    suggestions.create_suggestion(ids[0], "Undatiert", priority=3)
    suggestions.create_suggestion(ids[1], "Datierter Vorschlag", priority=3, suggested_date="2027-01-01")
    suggestions.create_suggestion(ids[2], "Vorrangig", priority=5, suggested_date="2027-06-01")
    assert [g["thread_id"] for g in today.list_today()["groups"]] == [ids[2], ids[1], ids[0]]
    assert suggestions.list_suggestions(thread_id=ids[1])[0]["suggested_date"] == date(2027, 1, 1)


def test_large_bundle_has_no_silent_200_card_cutoff(store):
    tid = threads.create_thread("Großer Bestand")
    with store() as conn:
        conn.cursor().executemany("INSERT INTO suggestions (thread_id, content) VALUES (%s, %s)",
                                  [(tid, f"Meldung {i}") for i in range(503)])
    result = today.list_today(mark_surfaced=False)
    assert result["total_count"] == 503
    assert result["groups"][0]["count"] == 503 and len(result["groups"][0]["cards"]) == 503
    assert suggestions.count_open_suggestions() == 503
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestions WHERE delivery_status='surfaced'").fetchone()[0] == 0


def test_deferred_groups_are_not_surface_or_response_events(store):
    tid = threads.create_thread("Warten")
    sid = suggestions.create_suggestion(tid, "Später prüfen")["suggestion_id"]
    suggestions.update_suggestion_status(sid, "deferred")
    result = today.list_today(status="deferred", mark_surfaced=True)
    assert result["total_count"] == 1 and result["groups"][0]["cards"][0]["delivery_status"] == "pending"
    with store() as conn:
        assert conn.execute("SELECT count(*) FROM suggestion_responses").fetchone()[0] == 0


def test_empty_and_invalid_pages(store):
    assert today.list_today(page=99) == {"groups": [], "total_count": 0, "group_count": 0, "page": 1, "page_count": 1}
    with pytest.raises(ValueError):
        today.list_today(page=0)
    with pytest.raises(ValueError):
        today.list_today(status="confirmed")
