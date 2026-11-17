"""Bounded review coverage and retry behavior in disposable PostgreSQL databases."""

import json

import pytest

from test_follow_up import store
from app.agent import evaluation
from app.storage import evaluation as state, suggestions, threads


def test_large_inventory_is_covered_without_losing_urgent_context(store, monkeypatch):
    ids = [threads.create_thread(f"Vorhaben {i}") for i in range(123)]
    threads.update_thread(ids[-1], deadline="2026-11-08")
    captured = []
    monkeypatch.setattr(evaluation, "list_memories", lambda **kw: [])
    def model(instructions, messages, tools, **kw):
        payload = json.loads(messages[0]["content"].split("\n", 1)[1])
        captured.append(payload)
        return "Keine neue Meldung."
    monkeypatch.setattr(evaluation, "run_tool_loop", model)
    for _ in range(3):
        evaluation._run_evaluation("scheduled")
    observed = set().union(*({t["id"] for t in item["offene_threads"]} for item in captured))
    assert observed == set(ids)
    assert all(ids[-1] in {t["id"] for t in item["offene_threads"]} for item in captured)
    assert all(len(item["offene_threads"]) <= 100 for item in captured)
    assert all(item["abdeckung"]["offene_gesamt"] == 123 for item in captured)
    assert state.latest_review_cursor() == 0
    assert all(row["review_cursor"] >= 0 for row in suggestions.list_runs())


def test_failed_evaluation_does_not_advance_review_cycle(store, monkeypatch):
    for i in range(52):
        threads.create_thread(f"Vorhaben {i}")
    monkeypatch.setattr(evaluation, "list_memories", lambda **kw: [])
    monkeypatch.setattr(evaluation, "run_tool_loop", lambda *a, **kw: "Kein Hinweis.")
    evaluation._run_evaluation()
    cursor = state.latest_review_cursor()
    assert cursor > 0
    def fail(*a, **kw):
        raise RuntimeError("Simulierter Modellfehler")
    monkeypatch.setattr(evaluation, "run_tool_loop", fail)
    with pytest.raises(RuntimeError):
        evaluation._run_evaluation()
    assert state.latest_review_cursor() == cursor
    monkeypatch.setattr(evaluation, "run_tool_loop", lambda *a, **kw: "Kein Hinweis.")
    evaluation._run_evaluation()
    assert state.latest_review_cursor() == 0


def test_page_metadata_and_closed_tail_wrap(store, monkeypatch):
    first = threads.create_thread("Aktiv")
    last = threads.create_thread("Danach abgeschlossen")
    threads.update_thread(last, status="completed")
    page = threads.list_thread_page(limit=1)
    assert page["total_count"] == 1 and page["threads"][0]["id"] == first
    assert not page["has_more"] and page["next_after_id"] is None
    run = suggestions.create_run()
    suggestions.finish_run(run, status="completed", review_cursor=last)
    monkeypatch.setattr(evaluation, "list_memories", lambda **kw: [])
    monkeypatch.setattr(evaluation, "run_tool_loop", lambda *a, **kw: "Kein Hinweis.")
    assert evaluation._run_evaluation()["threads_considered"] == 1
    assert state.latest_review_cursor() == 0
