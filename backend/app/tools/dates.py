"""Datums- und Zeitberechnung für Hugo.

Das Sprachmodell interpretiert die Bedeutung von Zeitangaben;
dieses Modul übernimmt die verlässliche Arithmetik.
"""

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

WEEKDAYS_DE = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)


def now_berlin() -> datetime:
    return datetime.now(BERLIN)


def today_berlin() -> date:
    return now_berlin().date()


def current_time_context() -> str:
    """Zeitkontext für den System-Prompt des Agenten."""
    now = now_berlin()
    return (
        "Aktuelles Datum und Uhrzeit: "
        f"{WEEKDAYS_DE[now.weekday()]}, "
        f"{now.strftime('%d.%m.%Y')}, "
        f"{now.strftime('%H:%M')} Uhr "
        f"(Zeitzone Europe/Berlin, ISO-Datum: {now.date().isoformat()})."
    )


def parse_date(value) -> date | None:
    """Wandelt eine Angabe in ein Datum um.

    Akzeptiert None, date, datetime oder ISO-8601-Text
    ('2027-03-15' oder '2027-03-15T10:00:00+01:00').
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        if "T" in text:
            return datetime.fromisoformat(
                text.replace("Z", "+00:00")
            ).date()
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"Ungültiges Datumsformat: {value!r}."
            " ISO 8601 erwartet, z. B. '2027-03-15'."
        )


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # Tag auf Monatsende begrenzen (31.01. + 1 Monat = 28./29.02.)
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def compute_date(
    base_date=None,
    days: int = 0,
    weeks: int = 0,
    months: int = 0,
    years: int = 0,
) -> dict:
    """Berechnet ein Datum relativ zu einem Basisdatum.

    Ohne Basisdatum wird der heutige Tag in Europe/Berlin
    verwendet. Monats- und Jahresoffsets werden zuerst
    angewendet (mit Begrenzung auf das Monatsende), danach
    Wochen und Tage.
    """
    base = parse_date(base_date) or today_berlin()

    months_total = (years or 0) * 12 + (months or 0)
    result = _add_months(base, months_total)
    result = result + timedelta(days=(days or 0) + (weeks or 0) * 7)

    return {
        "date": result.isoformat(),
        "weekday": WEEKDAYS_DE[result.weekday()],
        "base_date": base.isoformat(),
    }
