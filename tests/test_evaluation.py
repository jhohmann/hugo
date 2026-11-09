"""Unit-Tests für den Evaluationslauf der Proaktivitäts-Engine.

Laufen ohne Datenbank und ohne OpenAI-Zugriff:
Storage-Funktionen und die Werkzeugschleife werden ersetzt.
"""

import json

import pytest

from app.agent import evaluation


def test_werkzeugliste_der_bewertung():
    names = {tool["name"] for tool in evaluation.EVALUATION_TOOLS}

    # Lesen und Vorschläge erzeugen …
    assert "create_suggestion" in names
    assert "search_threads" in names
    assert "list_threads" in names
    assert "get_thread" in names
    assert "list_thread_events" in names
    assert "search_memories" in names
    assert "compute_date" in names

    # … aber keine Schreibzugriffe auf Threads/Erinnerungen.
    assert "create_thread" not in names
    assert "update_thread" not in names
    assert "create_memory" not in names
    assert "update_memory" not in names


@pytest.fixture
def fake_storage(monkeypatch):
    calls = {"finish_run": [], "create_run": []}

    def create_run(trigger="manual"):
        calls["create_run"].append(trigger)
        return 1

    def finish_run(run_id, **kwargs):
        calls["finish_run"].append(kwargs)

    monkeypatch.setattr(evaluation, "create_run", create_run)
    monkeypatch.setattr(evaluation, "finish_run", finish_run)
    monkeypatch.setattr(evaluation, "list_threads", lambda **kw: [])
    monkeypatch.setattr(
        evaluation, "list_memories", lambda limit=30: []
    )
    monkeypatch.setattr(
        evaluation, "list_suggestions", lambda **kw: []
    )
    monkeypatch.setattr(
        evaluation, "count_suggestions_for_run", lambda run_id: 0
    )
    return calls


def test_leerer_bestand_erzeugt_keine_vorschlaege(
    fake_storage, monkeypatch
):
    captured = {}

    def fake_loop(instructions, messages, tools, **kwargs):
        captured["tools"] = {t["name"] for t in tools}
        captured["instructions"] = instructions
        return "Kein Handlungsbedarf erkannt."

    monkeypatch.setattr(evaluation, "run_tool_loop", fake_loop)

    result = evaluation.run_evaluation()

    assert result["status"] == "completed"
    assert result["threads_considered"] == 0
    assert result["suggestions_created"] == 0
    assert result["summary"] == "Kein Handlungsbedarf erkannt."
    # Zeitkontext wird auch bei der Bewertung injiziert
    assert "Europe/Berlin" in captured["instructions"]
    assert "ZEITKONTEXT" in captured["instructions"]
    # Lauf wurde nachvollziehbar abgeschlossen
    assert fake_storage["create_run"] == ["manual"]
    assert fake_storage["finish_run"][0]["status"] == "completed"


def test_bestand_und_run_id_werden_uebergeben(
    fake_storage, monkeypatch
):
    monkeypatch.setattr(
        evaluation,
        "list_threads",
        lambda **kw: [{"id": 7, "title": "Japan-Reise"}],
    )
    monkeypatch.setattr(
        evaluation,
        "list_memories",
        lambda limit=30: [{"id": 3, "content": "Pass gültig"}],
    )
    monkeypatch.setattr(
        evaluation,
        "list_suggestions",
        lambda **kw: [
            {"id": 5, "status": "open", "content": "Alt"},
            {"id": 6, "status": "dismissed", "content": "Verworfen"},
        ],
    )
    captured = {}

    def fake_loop(instructions, messages, tools, **kwargs):
        captured["content"] = messages[0]["content"]
        captured["run_id"] = kwargs.get("run_id")
        return "ok"

    monkeypatch.setattr(evaluation, "run_tool_loop", fake_loop)

    result = evaluation.run_evaluation()

    assert result["threads_considered"] == 1
    assert captured["run_id"] == 1
    # Threads, Erinnerungen und bestehende offene Vorschläge
    # stehen im Bewertungskontext; verworfene nicht.
    assert "Japan-Reise" in captured["content"]
    assert "Pass gültig" in captured["content"]
    assert "Alt" in captured["content"]
    assert "Verworfen" not in captured["content"]


def test_scheduled_evaluation_keeps_paused_plans_as_context(fake_storage, monkeypatch):
    plans = [
        {"id": 1, "title": "Offenes Ziel", "act_by": None},
        {"id": 2, "title": "Später prüfen", "review_on": "2099-01-01"},
    ]

    def read_threads(**kwargs):
        assert kwargs.get("open_only") is True
        assert not kwargs.get("review_due_only", False)
        assert kwargs.get("tag") is None
        return plans

    def model_loop(instructions, messages, tools, **kwargs):
        payload = json.loads(messages[0]["content"].split("\n", 1)[1])
        assert payload["offene_threads"] == plans
        return "Kein neuer Anlass."

    monkeypatch.setattr(evaluation, "list_threads", read_threads)
    monkeypatch.setattr(evaluation, "run_tool_loop", model_loop)
    result = evaluation.run_evaluation(trigger="scheduled")
    assert result["threads_considered"] == 2
    assert fake_storage["create_run"] == ["scheduled"]


def test_fehler_markiert_lauf_als_failed(
    fake_storage, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("OpenAI nicht erreichbar")

    monkeypatch.setattr(evaluation, "run_tool_loop", boom)

    with pytest.raises(RuntimeError, match="OpenAI"):
        evaluation.run_evaluation()

    assert fake_storage["finish_run"][0]["status"] == "failed"
    assert "OpenAI nicht erreichbar" in (
        fake_storage["finish_run"][0]["error"]
    )
