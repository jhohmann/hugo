"""Unit-Tests für die Thread-Werkzeuge des zentralen Agenten.

Laufen ohne Datenbank und ohne OpenAI-Zugriff:
Die Storage-Funktionen werden ersetzt (monkeypatch).
"""

import pytest

from app.agent import assistant
from app.storage import threads as thread_storage


@pytest.fixture
def fake_storage(monkeypatch):
    calls = {}

    def record(name):
        def fake(*args, **kwargs):
            calls.setdefault(name, []).append(
                {"args": args, "kwargs": kwargs}
            )
            return fake.return_value
        return fake

    for name in (
        "search_threads",
        "list_threads",
        "get_thread",
        "create_thread",
        "update_thread",
        "create_suggestion",
    ):
        monkeypatch.setattr(assistant, name, record(name))

    return calls


def test_create_thread_reicht_felder_und_quelle_weiter(fake_storage):
    assistant.create_thread.return_value = 7

    result = assistant.execute_tool(
        "create_thread",
        {
            "title": "Norwegen-Reise",
            "description": "Roadtrip durch die Fjorde",
            "status": "active",
            "priority": 3,
            "deadline": "2026-06-15",
            "event_start": None,
            "event_end": None,
            "time_precision": None,
            "act_by": None,
            "time_text": None,
            "next_action": "Fähre recherchieren",
        },
        source_message_id=42,
    )

    assert result == {"thread_id": 7}
    kwargs = fake_storage["create_thread"][0]["kwargs"]
    assert kwargs["status"] == "active"
    assert kwargs["deadline"] == "2026-06-15"
    assert kwargs["source_message_id"] == 42


def test_create_thread_reicht_zeitfelder_weiter(fake_storage):
    assistant.create_thread.return_value = 8

    assistant.execute_tool(
        "create_thread",
        {
            "title": "Japan-Reise",
            "description": None,
            "status": "active",
            "priority": None,
            "deadline": None,
            "event_start": "2027-03-15",
            "event_end": "2027-03-29",
            "time_precision": "exact",
            "act_by": "2027-01-15",
            "time_text": "am 15. März für zwei Wochen",
            "next_action": "Flüge vergleichen",
        },
        source_message_id=1,
    )

    kwargs = fake_storage["create_thread"][0]["kwargs"]
    assert kwargs["event_start"] == "2027-03-15"
    assert kwargs["event_end"] == "2027-03-29"
    assert kwargs["time_precision"] == "exact"
    assert kwargs["act_by"] == "2027-01-15"
    assert kwargs["time_text"] == "am 15. März für zwei Wochen"


def test_update_thread_nur_explizite_felder(fake_storage):
    assistant.update_thread.return_value = {"id": 3}

    result = assistant.execute_tool(
        "update_thread",
        {
            "thread_id": 3,
            "title": None,
            "description": None,
            "status": "active",
            "priority": None,
            "deadline": None,
            "event_start": None,
            "event_end": None,
            "time_precision": None,
            "act_by": None,
            "time_text": None,
            "next_action": None,
        },
        source_message_id=1,
    )

    kwargs = fake_storage["update_thread"][0]["kwargs"]
    # Nur status wurde übergeben; null-Felder bleiben unangetastet.
    assert kwargs == {
        "status": "active",
        "source_message_id": 1,
    }
    assert result["updated"] is True


def test_update_thread_nur_act_by(fake_storage):
    assistant.update_thread.return_value = {"id": 3}

    assistant.execute_tool(
        "update_thread",
        {
            "thread_id": 3,
            "title": None,
            "description": None,
            "status": None,
            "priority": None,
            "deadline": None,
            "event_start": None,
            "event_end": None,
            "time_precision": None,
            "act_by": "2027-01-15",
            "time_text": None,
            "next_action": None,
        },
        source_message_id=1,
    )

    kwargs = fake_storage["update_thread"][0]["kwargs"]
    assert kwargs == {
        "act_by": "2027-01-15",
        "source_message_id": 1,
    }


def test_update_thread_ohne_aenderungen_ruft_storage_nicht(
    fake_storage,
):
    result = assistant.execute_tool(
        "update_thread",
        {
            "thread_id": 3,
            "title": None,
            "description": None,
            "status": None,
            "priority": None,
            "deadline": None,
            "next_action": None,
        },
        source_message_id=1,
    )

    assert result == {
        "thread_id": 3,
        "updated": False,
        "reason": "no_changes",
    }
    assert "update_thread" not in fake_storage


def test_update_thread_unbekannte_id(fake_storage):
    assistant.update_thread.return_value = None

    result = assistant.execute_tool(
        "update_thread",
        {
            "thread_id": 999,
            "title": None,
            "description": None,
            "status": "active",
            "priority": None,
            "deadline": None,
            "next_action": None,
        },
        source_message_id=1,
    )

    assert result == {
        "thread_id": 999,
        "updated": False,
        "reason": "not_found",
    }


def test_get_thread_nicht_gefunden(fake_storage):
    assistant.get_thread.return_value = None

    result = assistant.execute_tool(
        "get_thread",
        {"thread_id": 999},
        source_message_id=1,
    )

    assert result == {"thread_id": 999, "found": False}


def test_search_threads_begrenzt_limit(fake_storage):
    assistant.search_threads.return_value = []

    assistant.execute_tool(
        "search_threads",
        {"query": "Norwegen", "status": None, "limit": 99},
        source_message_id=1,
    )

    kwargs = fake_storage["search_threads"][0]["kwargs"]
    assert kwargs["limit"] == 10
    assert kwargs["status"] is None


def test_unbekanntes_werkzeug_wirft_fehler():
    with pytest.raises(ValueError, match="Unknown tool"):
        assistant.execute_tool(
            "delete_everything",
            {},
            source_message_id=1,
        )


def test_compute_date_werkzeug():
    result = assistant.execute_tool(
        "compute_date",
        {
            "base_date": "2026-11-03",
            "days": None,
            "weeks": None,
            "months": 3,
            "years": None,
        },
        source_message_id=1,
    )

    assert result["date"] == "2027-02-03"
    assert result["weekday"] == "Mittwoch"
    assert result["base_date"] == "2026-11-03"


def test_build_instructions_enthaelt_zeitkontext():
    instructions = assistant.build_instructions()
    assert "ZEITKONTEXT" in instructions
    assert "Europe/Berlin" in instructions
    assert assistant.SYSTEM_PROMPT.strip()[:30] in instructions


def test_create_suggestion_reicht_run_id_weiter(fake_storage):
    assistant.create_suggestion.return_value = {
        "suggestion_id": 11,
        "created": True,
    }

    result = assistant.execute_tool(
        "create_suggestion",
        {
            "thread_id": 7,
            "content": "Flugbuchung jetzt angehen.",
            "reason": "Reisebeginn rückt näher.",
            "priority": 4,
            "suggested_date": "2026-11-10",
        },
        run_id=3,
    )

    assert result == {"suggestion_id": 11, "created": True}
    args = fake_storage["create_suggestion"][0]
    assert args["args"][0] == 7
    assert args["args"][1] == "Flugbuchung jetzt angehen."
    assert args["kwargs"]["priority"] == 4
    assert args["kwargs"]["run_id"] == 3


# Validierung in der Storage-Schicht (ohne Datenbankzugriff,
# da die Prüfung vor jeder Abfrage erfolgt).

def test_status_validierung():
    with pytest.raises(ValueError, match="Status"):
        thread_storage._validate_status("vergessen")
    assert thread_storage._validate_status("proposed") == "proposed"
    assert thread_storage._validate_status(None) is None


def test_prioritaet_validierung():
    with pytest.raises(ValueError, match="Priorität"):
        thread_storage._validate_priority(6)
    with pytest.raises(ValueError, match="Priorität"):
        thread_storage._validate_priority(0)
    assert thread_storage._validate_priority(3) == 3


def test_deadline_validierung():
    with pytest.raises(ValueError, match="Datumsformat"):
        thread_storage._parse_deadline("bald irgendwann")

    parsed = thread_storage._parse_deadline("2026-06-15")
    assert parsed.year == 2026
    assert parsed.tzinfo is not None

    parsed_z = thread_storage._parse_deadline(
        "2026-06-15T10:00:00Z"
    )
    assert parsed_z.utcoffset().total_seconds() == 0


def test_time_precision_validierung():
    with pytest.raises(ValueError, match="Genauigkeit"):
        thread_storage._validate_time_precision("vage")
    assert (
        thread_storage._validate_time_precision("approximate")
        == "approximate"
    )
    assert thread_storage._validate_time_precision(None) is None


def test_event_range_validierung():
    from datetime import date

    # Ende ohne Beginn ist ungültig
    with pytest.raises(ValueError, match="event_start"):
        thread_storage._validate_event_range(
            None, date(2027, 6, 20)
        )

    # Ende vor Beginn ist ungültig
    with pytest.raises(ValueError, match="vor event_start"):
        thread_storage._validate_event_range(
            date(2027, 6, 20), date(2027, 6, 10)
        )

    # Gültige Fälle
    thread_storage._validate_event_range(date(2027, 6, 10), None)
    thread_storage._validate_event_range(
        date(2027, 6, 10), date(2027, 6, 20)
    )
    thread_storage._validate_event_range(None, None)
