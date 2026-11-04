"""Unit-Tests für die Datumsberechnung (kein DB-/OpenAI-Zugriff)."""

from datetime import date, datetime

import pytest

from app.tools.dates import (
    BERLIN,
    compute_date,
    current_time_context,
    now_berlin,
    parse_date,
    today_berlin,
)


# --- parse_date ---

def test_parse_date_iso_text():
    assert parse_date("2027-03-15") == date(2027, 3, 15)


def test_parse_date_datetime_und_date():
    assert parse_date(date(2027, 3, 15)) == date(2027, 3, 15)
    assert parse_date(datetime(2027, 3, 15, 10, 30)) == date(
        2027, 3, 15
    )


def test_parse_date_iso_mit_zeitzone():
    assert parse_date("2027-03-15T10:00:00Z") == date(2027, 3, 15)
    assert parse_date("2027-03-15T10:00:00+01:00") == date(
        2027, 3, 15
    )


def test_parse_date_none_und_ungueltig():
    assert parse_date(None) is None
    with pytest.raises(ValueError, match="Datumsformat"):
        parse_date("bald irgendwann")


# --- compute_date: absolute Offsets ---

def test_compute_date_tage():
    result = compute_date("2026-11-03", days=10)
    assert result["date"] == "2026-11-13"
    assert result["weekday"] == "Freitag"
    assert result["base_date"] == "2026-11-03"


def test_compute_date_wochen():
    result = compute_date("2026-11-03", weeks=2)
    assert result["date"] == "2026-11-17"
    assert result["weekday"] == "Dienstag"


def test_compute_date_monate_ueber_jahreswechsel():
    result = compute_date("2026-11-03", months=3)
    assert result["date"] == "2027-02-03"
    assert result["weekday"] == "Mittwoch"


def test_compute_date_jahre():
    result = compute_date("2026-11-03", years=1)
    assert result["date"] == "2027-11-03"


def test_compute_date_negative_offsets():
    result = compute_date("2026-11-03", days=-1, months=-1)
    # Monate werden zuerst angewendet: 03.10.2026, dann -1 Tag
    assert result["date"] == "2026-10-02"


def test_compute_date_monatsende_begrenzung():
    # 31.01. + 1 Monat: 2026 ist kein Schaltjahr
    assert compute_date("2026-01-31", months=1)["date"] == "2026-02-28"
    # 2028 ist ein Schaltjahr
    assert compute_date("2028-01-31", months=1)["date"] == "2028-02-29"


def test_compute_date_kombiniert():
    result = compute_date(
        "2026-11-03", years=1, months=1, weeks=1, days=1
    )
    # 03.11.2026 + 1 Jahr = 03.11.2027; + 1 Monat = 03.12.2027;
    # + 1 Woche = 10.12.2027; + 1 Tag = 11.12.2027
    assert result["date"] == "2027-12-11"


def test_compute_date_standard_ist_heute_berlin():
    result = compute_date(days=0)
    assert result["date"] == today_berlin().isoformat()


# --- Zeitkontext ---

def test_zeitkontext_enthaelt_berlin_und_wochentag():
    context = current_time_context()
    assert "Europe/Berlin" in context
    assert any(
        tag in context
        for tag in (
            "Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag",
        )
    )


def test_now_berlin_hat_zeitzone():
    assert now_berlin().tzinfo is not None
    assert BERLIN.key == "Europe/Berlin"
