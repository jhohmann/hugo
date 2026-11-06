"""Integrations-Tests für Vorschläge und Evaluationsläufe.

Benötigen eine erreichbare PostgreSQL-Datenbank
(inkl. Migration 001_initial.sql).
Werden übersprungen, wenn keine Datenbank läuft.
"""

from datetime import date

import pytest

from app.storage.database import get_connection
from app.storage.suggestions import (
    count_suggestions_for_run,
    create_run,
    create_suggestion,
    finish_run,
    list_runs,
    list_suggestions,
    update_suggestion_status,
)
from app.storage.threads import create_thread


def _db_available() -> bool:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="Datenbank nicht erreichbar",
)


@pytest.fixture
def cleanup():
    """Räumt nur die vom Test angelegten Datensätze ab."""
    ids = {"suggestions": [], "runs": [], "threads": []}
    yield ids
    with get_connection() as conn:
        if ids["suggestions"]:
            conn.execute(
                "DELETE FROM suggestions WHERE id = ANY(%s)",
                (ids["suggestions"],),
            )
        if ids["threads"]:
            conn.execute(
                "DELETE FROM thread_messages"
                " WHERE thread_id = ANY(%s)",
                (ids["threads"],),
            )
            conn.execute(
                "DELETE FROM threads WHERE id = ANY(%s)",
                (ids["threads"],),
            )
        if ids["runs"]:
            conn.execute(
                "DELETE FROM evaluation_runs WHERE id = ANY(%s)",
                (ids["runs"],),
            )


def _suggestion(cleanup, **kwargs) -> dict:
    result = create_suggestion(**kwargs)
    cleanup["suggestions"].append(result["suggestion_id"])
    return result


# --- Evaluationsläufe ---

def test_run_lebenszyklus(cleanup):
    run_id = create_run("manual")
    cleanup["runs"].append(run_id)

    finish_run(
        run_id,
        status="completed",
        threads_considered=3,
        suggestions_created=1,
    )

    runs = list_runs()
    run = next(r for r in runs if r["id"] == run_id)
    assert run["status"] == "completed"
    assert run["trigger_source"] == "manual"
    assert run["threads_considered"] == 3
    assert run["suggestions_created"] == 1
    assert run["finished_at"] is not None
    assert run["error"] is None


def test_run_fehlerfall(cleanup):
    run_id = create_run()
    cleanup["runs"].append(run_id)

    finish_run(run_id, status="failed", error="OpenAI down")

    run = next(r for r in list_runs() if r["id"] == run_id)
    assert run["status"] == "failed"
    assert run["error"] == "OpenAI down"


def test_run_ungueltiger_trigger_und_status():
    with pytest.raises(ValueError, match="Trigger"):
        create_run("weekly")
    with pytest.raises(ValueError, match="Lauf-Status"):
        finish_run(1, status="running")


# --- Vorschläge ---

def test_suggestion_roundtrip(cleanup):
    thread_id = create_thread("Japan-Reise", status="active")
    cleanup["threads"].append(thread_id)
    run_id = create_run()
    cleanup["runs"].append(run_id)

    result = _suggestion(
        cleanup,
        thread_id=thread_id,
        content="Flugbuchung jetzt angehen.",
        reason="Reisebeginn rückt näher.",
        priority=4,
        suggested_date="2026-11-10",
        run_id=run_id,
    )

    assert result["created"] is True
    assert count_suggestions_for_run(run_id) == 1

    found = next(
        s for s in list_suggestions()
        if s["id"] == result["suggestion_id"]
    )
    assert found["thread_id"] == thread_id
    assert found["run_id"] == run_id
    assert found["priority"] == 4
    assert found["suggested_date"] == date(2026, 11, 10)
    assert found["delivery_status"] == "pending"
    assert found["status"] == "open"


def test_suggestion_dedupe_identisch(cleanup):
    thread_id = create_thread("Norwegen-Reise")
    cleanup["threads"].append(thread_id)

    first = _suggestion(
        cleanup, thread_id=thread_id, content="Fähre buchen."
    )
    # Gleicher Text mit anderer Groß-/Kleinschreibung
    # und Leerzeichen → kein neuer Vorschlag.
    second = create_suggestion(
        thread_id, "  fähre buchen.  "
    )

    assert second["created"] is False
    assert second["reason"] == "duplicate"
    assert second["suggestion_id"] == first["suggestion_id"]


def test_suggestion_dedupe_auch_nach_verwerfen(cleanup):
    thread_id = create_thread("Norwegen-Reise")
    cleanup["threads"].append(thread_id)

    first = _suggestion(
        cleanup, thread_id=thread_id, content="Fähre buchen."
    )
    update_suggestion_status(first["suggestion_id"], "dismissed")

    second = create_suggestion(thread_id, "Fähre buchen.")
    assert second["created"] is False

    # Anderer Text → neuer Vorschlag möglich
    third = _suggestion(
        cleanup, thread_id=thread_id, content="Unterkunft suchen."
    )
    assert third["created"] is True


def test_suggestion_dedupe_thread_scoped(cleanup):
    thread_a = create_thread("Vorhaben A")
    thread_b = create_thread("Vorhaben B")
    cleanup["threads"].extend([thread_a, thread_b])

    first = _suggestion(
        cleanup, thread_id=thread_a, content="Nachfassen."
    )
    # Gleicher Text bei anderem Thread → erlaubt
    second = _suggestion(
        cleanup, thread_id=thread_b, content="Nachfassen."
    )
    assert second["created"] is True
    assert second["suggestion_id"] != first["suggestion_id"]

    # Ohne Thread-Bezug: dedupe untereinander
    third = _suggestion(cleanup, thread_id=None, content="Allgemein.")
    fourth = create_suggestion(None, "Allgemein.")
    assert fourth["created"] is False
    assert fourth["suggestion_id"] == third["suggestion_id"]


def test_suggestion_validierung(cleanup):
    thread_id = create_thread("Validierung")
    cleanup["threads"].append(thread_id)

    with pytest.raises(ValueError, match="Leerer"):
        create_suggestion(thread_id, "   ")
    with pytest.raises(ValueError, match="Priorität"):
        create_suggestion(thread_id, "Text", priority=6)
    with pytest.raises(ValueError, match="Datumsformat"):
        create_suggestion(
            thread_id, "Text", suggested_date="bald"
        )
    with pytest.raises(ValueError, match="nicht gefunden"):
        create_suggestion(999999999, "Text")


def test_suggestion_statuswechsel(cleanup):
    result = _suggestion(
        cleanup, thread_id=None, content="Statuswechsel."
    )
    suggestion_id = result["suggestion_id"]

    confirmed = update_suggestion_status(suggestion_id, "confirmed")
    assert confirmed["status"] == "confirmed"

    deferred = update_suggestion_status(suggestion_id, "deferred")
    assert deferred["status"] == "deferred"

    dismissed = update_suggestion_status(suggestion_id, "dismissed")
    assert dismissed["status"] == "dismissed"

    assert update_suggestion_status(999999999, "dismissed") is None

    with pytest.raises(ValueError, match="Status"):
        update_suggestion_status(suggestion_id, "erledigt")


def test_list_suggestions_filter_und_zustellung(cleanup):
    first = _suggestion(
        cleanup, thread_id=None, content="Erster.", priority=2
    )
    second = _suggestion(
        cleanup, thread_id=None, content="Zweiter.", priority=5
    )

    # Zustellung: Zurückgegebene Vorschläge werden 'surfaced'
    pending = list_suggestions(delivery="pending")
    pending_ids = {s["id"] for s in pending}
    assert first["suggestion_id"] in pending_ids

    surfaced = list_suggestions(mark_surfaced=True)
    surfaced_by_id = {s["id"]: s for s in surfaced}
    assert (
        surfaced_by_id[first["suggestion_id"]]["delivery_status"]
        == "surfaced"
    )

    # Danach nicht mehr pending
    pending_after = list_suggestions(delivery="pending")
    assert all(
        s["id"] != first["suggestion_id"] for s in pending_after
    )

    # Höhere Priorität zuerst
    offene = list_suggestions(status="open")
    ids = [s["id"] for s in offene]
    assert ids.index(second["suggestion_id"]) < ids.index(
        first["suggestion_id"]
    )
