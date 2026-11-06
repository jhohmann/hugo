"""Integrations-Tests für die Thread-Storage-Schicht.

Benötigen eine erreichbare PostgreSQL-Datenbank
(inkl. Migration 001_initial.sql).
Werden übersprungen, wenn keine Datenbank läuft.
"""

from datetime import date

import pytest

from app.storage.database import (
    create_conversation,
    get_connection,
    save_message,
)
from app.storage.threads import (
    create_thread,
    get_thread,
    list_threads,
    search_threads,
    update_thread,
)


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
def thread_ids():
    """Räumt nur die vom Test angelegten Threads wieder ab."""
    created = []
    yield created
    if not created:
        return
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM thread_messages"
            " WHERE thread_id = ANY(%s)",
            (created,),
        )
        conn.execute(
            "DELETE FROM threads WHERE id = ANY(%s)",
            (created,),
        )


def test_create_und_get_thread(thread_ids):
    thread_id = create_thread(
        "Norwegen-Reise planen",
        description="Roadtrip durch die Fjorde",
        status="active",
        priority=4,
        deadline="2026-06-15",
        next_action="Fähre recherchieren",
    )
    thread_ids.append(thread_id)

    thread = get_thread(thread_id)

    assert thread is not None
    assert thread["title"] == "Norwegen-Reise planen"
    assert thread["status"] == "active"
    assert thread["priority"] == 4
    assert thread["deadline"].year == 2026
    assert thread["next_action"] == "Fähre recherchieren"


def test_create_thread_standard_ist_unverbindlich(thread_ids):
    thread_id = create_thread("Vielleicht ein Gartenhaus")
    thread_ids.append(thread_id)

    thread = get_thread(thread_id)

    # Ohne expliziten Status bleibt es eine Überlegung.
    assert thread["status"] == "proposed"
    assert thread["priority"] is None
    assert thread["deadline"] is None


def test_create_thread_verknuepft_quellnachricht(thread_ids):
    conversation_id = create_conversation()
    message_id = save_message(
        conversation_id, "user", "Testnachricht"
    )

    thread_id = create_thread(
        "Haus modernisieren",
        source_message_id=message_id,
    )
    thread_ids.append(thread_id)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM thread_messages"
            " WHERE thread_id = %s AND message_id = %s",
            (thread_id, message_id),
        ).fetchone()

    assert row[0] == 1

    # Aufräumen der Test-Konversation
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM messages WHERE id = %s",
            (message_id,),
        )
        conn.execute(
            "DELETE FROM conversations WHERE id = %s",
            (conversation_id,),
        )


def test_create_thread_mit_blocked_reason_und_preparation_weeks(thread_ids):
    thread_id = create_thread(
        "Japan-Reise",
        status="active",
        blocked_reason="Visum noch nicht beantragt",
        preparation_weeks=12,
    )
    thread_ids.append(thread_id)

    thread = get_thread(thread_id)

    assert thread["blocked_reason"] == "Visum noch nicht beantragt"
    assert thread["preparation_weeks"] == 12


def test_update_thread_mit_blocked_reason_und_preparation_weeks(thread_ids):
    thread_id = create_thread("Norwegen-Reise", status="active")
    thread_ids.append(thread_id)

    update_thread(
        thread_id,
        blocked_reason="Warte auf Rückmeldung",
        preparation_weeks=8,
    )

    thread = get_thread(thread_id)
    assert thread["blocked_reason"] == "Warte auf Rückmeldung"
    assert thread["preparation_weeks"] == 8


def test_update_thread_laesst_andere_threads_unveraendert(
    thread_ids,
):
    reise = create_thread(
        "Norwegen-Reise planen", status="proposed"
    )
    motorrad = create_thread(
        "Motorrad-Reifen wechseln",
        status="active",
        next_action="Werkstatttermin vereinbaren",
    )
    thread_ids.extend([reise, motorrad])

    vorher = get_thread(motorrad)

    updated = update_thread(
        reise,
        status="active",
        deadline="2026-06-15",
        next_action="Fähre buchen",
    )

    assert updated["status"] == "active"
    assert updated["next_action"] == "Fähre buchen"
    assert updated["deadline"] is not None

    nachher = get_thread(motorrad)
    assert nachher == vorher


def test_update_thread_teilupdate_behält_rest(thread_ids):
    thread_id = create_thread(
        "Norwegen-Reise planen",
        description="Roadtrip durch die Fjorde",
        next_action="Fähre recherchieren",
    )
    thread_ids.append(thread_id)

    updated = update_thread(thread_id, status="active")

    assert updated["status"] == "active"
    assert updated["description"] == "Roadtrip durch die Fjorde"
    assert updated["next_action"] == "Fähre recherchieren"


def test_update_thread_unbekannte_id_gibt_none():
    assert update_thread(999999999, status="active") is None


def test_list_threads_offene_vor_abgeschlossenen(thread_ids):
    offen = create_thread("Offenes Vorhaben", status="active")
    fertig = create_thread(
        "Erledigtes Vorhaben", status="completed"
    )
    thread_ids.extend([offen, fertig])

    threads = list_threads()
    by_id = {t["id"]: i for i, t in enumerate(threads)}

    assert by_id[offen] < by_id[fertig]

    nur_aktive = list_threads(status="active")
    assert all(
        t["status"] == "active" for t in nur_aktive
    )


def test_search_threads_findet_thematisch_passende(thread_ids):
    reise = create_thread(
        "Norwegen-Reise planen",
        description="Roadtrip durch die Fjorde im Sommer",
    )
    motorrad = create_thread("Motorrad-Reifen wechseln")
    thread_ids.extend([reise, motorrad])

    results = search_threads("Urlaub in Skandinavien", limit=5)

    assert results
    assert results[0]["id"] == reise
    assert "similarity" in results[0]


def test_search_threads_mit_statusfilter(thread_ids):
    überlegung = create_thread(
        "Island-Option prüfen", status="proposed"
    )
    vorhaben = create_thread(
        "Norwegen-Reise buchen", status="active"
    )
    thread_ids.extend([überlegung, vorhaben])

    results = search_threads(
        "Reise", status="active", limit=10
    )

    assert results
    assert all(t["status"] == "active" for t in results)
    assert all(t["id"] != überlegung for t in results)


# --- Zeitfelder (Temporal Reasoning) ---


def test_thread_mit_exaktem_termin(thread_ids):
    thread_id = create_thread(
        "Japan-Reise",
        status="active",
        event_start="2027-03-15",
        event_end="2027-03-29",
        time_precision="exact",
        act_by="2027-01-15",
        time_text="am 15. März für zwei Wochen",
        next_action="Flüge vergleichen",
    )
    thread_ids.append(thread_id)

    thread = get_thread(thread_id)

    assert thread["event_start"] == date(2027, 3, 15)
    assert thread["event_end"] == date(2027, 3, 29)
    assert thread["time_precision"] == "exact"
    assert thread["act_by"] == date(2027, 1, 15)
    assert thread["time_text"] == "am 15. März für zwei Wochen"


def test_thread_mit_ungefaehrem_zeitraum(thread_ids):
    """Ungefähre Angabe: Zeitraum + approximate, Originaltext
    bleibt erhalten, keine erfundene harte Frist."""
    thread_id = create_thread(
        "Schottland-Roadtrip",
        status="proposed",
        event_start="2027-08-10",
        event_end="2027-08-25",
        time_precision="approximate",
        time_text="so ungefähr Mitte August nächstes Jahr",
    )
    thread_ids.append(thread_id)

    thread = get_thread(thread_id)

    assert thread["time_precision"] == "approximate"
    assert thread["event_end"] > thread["event_start"]
    assert thread["time_text"] == (
        "so ungefähr Mitte August nächstes Jahr"
    )
    assert thread["deadline"] is None


def test_thread_standard_genauigkeit_ist_exact(thread_ids):
    thread_id = create_thread("Einfaches Vorhaben")
    thread_ids.append(thread_id)

    thread = get_thread(thread_id)

    assert thread["time_precision"] == "exact"
    assert thread["event_start"] is None
    assert thread["act_by"] is None


def test_event_range_validierung_gegen_db(thread_ids):
    # Ende ohne Beginn
    with pytest.raises(ValueError, match="event_start"):
        create_thread("Ungültig", event_end="2027-06-20")

    # Ende vor Beginn
    with pytest.raises(ValueError, match="vor event_start"):
        create_thread(
            "Ungültig",
            event_start="2027-06-20",
            event_end="2027-06-10",
        )


def test_update_thread_zeitraum_gegen_bestand(thread_ids):
    thread_id = create_thread(
        "Norwegen-Reise", event_start="2027-06-10"
    )
    thread_ids.append(thread_id)

    # Gültiges Teil-Update: Ende nach gespeichertem Beginn
    updated = update_thread(thread_id, event_end="2027-06-24")
    assert updated["event_start"] == date(2027, 6, 10)
    assert updated["event_end"] == date(2027, 6, 24)

    # Ungültig: neues Ende vor gespeichertem Beginn
    with pytest.raises(ValueError, match="vor event_start"):
        update_thread(thread_id, event_end="2027-06-01")


def test_update_ohne_zeitfelder_laesst_sie_unveraendert(
    thread_ids,
):
    thread_id = create_thread(
        "Japan-Reise",
        status="proposed",
        event_start="2027-03-15",
        act_by="2027-01-15",
        time_text="am 15. März",
    )
    thread_ids.append(thread_id)

    updated = update_thread(thread_id, status="active")

    assert updated["status"] == "active"
    assert updated["event_start"] == date(2027, 3, 15)
    assert updated["act_by"] == date(2027, 1, 15)
    assert updated["time_text"] == "am 15. März"


def test_list_threads_ordnet_nach_handlungszeitpunkt(
    thread_ids,
):
    ohne_datum = create_thread("Ohne Datum")
    bald_faellig = create_thread(
        "Bald fällig", act_by=date(2026, 11, 10)
    )
    thread_ids.extend([ohne_datum, bald_faellig])

    threads = list_threads()
    by_id = {t["id"]: i for i, t in enumerate(threads)}

    assert by_id[bald_faellig] < by_id[ohne_datum]


def test_list_threads_open_only(thread_ids):
    offen = create_thread("Offen", status="active")
    fertig = create_thread("Fertig", status="completed")
    archiviert = create_thread("Archiviert", status="archived")
    thread_ids.extend([offen, fertig, archiviert])

    offene = list_threads(open_only=True)
    ids = {t["id"] for t in offene}

    assert offen in ids
    assert fertig not in ids
    assert archiviert not in ids
