"""Darstellungshilfen für die Weboberfläche (de-DE).

Reine Präsentationslogik: Datumsformate, Wochentage,
relative Tageshinweise und Status-/Prioritäts-Labels.
"""

from datetime import date, datetime

from app.calendar import service as calendar_service
from app.tools.dates import BERLIN, WEEKDAYS_DE, parse_date, today_berlin

THREAD_STATUS_LABELS = {
    "proposed": "Idee",
    "active": "Aktiv",
    "waiting": "Wartet",
    "completed": "Erledigt",
    "archived": "Archiviert",
}

THREAD_TAG_LABELS = {"arbeit": "Arbeit", "privat": "Privat"}

SUGGESTION_STATUS_LABELS = {
    "open": "Offen",
    "confirmed": "Bestätigt",
    "deferred": "Zurückgestellt",
    "dismissed": "Verworfen",
}

ACTION_TYPE_LABELS = {
    "create": "Neuer Termin",
    "update": "Termin ändern",
    "delete": "Termin löschen",
}

ACTION_STATUS_LABELS = {
    "pending": "Wartet auf Bestätigung",
    "confirmed": "Bestätigt",
    "rejected": "Abgelehnt",
    "executed": "Ausgeführt",
    "failed": "Fehlgeschlagen",
    "conflict": "Konflikt erkannt",
}


def de_date(value) -> str:
    """'15.03.2027' oder '—'."""
    parsed = parse_date(value)
    return parsed.strftime("%d.%m.%Y") if parsed else "—"


def de_datetime(value) -> str:
    """'15.03.2027, 14:30 Uhr' oder '—'. Aware Daten → Europe/Berlin."""
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return de_date(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(BERLIN)
        return value.strftime("%d.%m.%Y, %H:%M Uhr")
    return de_date(value)


def de_weekday(value) -> str:
    parsed = parse_date(value)
    return WEEKDAYS_DE[parsed.weekday()] if parsed else ""


def days_until(value, today: date | None = None) -> int | None:
    """Tage bis zum Datum; negativ = vergangen."""
    parsed = parse_date(value)
    if parsed is None:
        return None
    return (parsed - (today or today_berlin())).days


def relative_label(value, today: date | None = None) -> str:
    """'heute', 'morgen', 'in 5 Tagen', 'seit 2 Tagen'."""
    days = days_until(value, today)
    if days is None:
        return ""
    if days == 0:
        return "heute"
    if days == 1:
        return "morgen"
    if days == -1:
        return "seit gestern"
    if days > 1:
        return f"in {days} Tagen"
    return f"seit {-days} Tagen"


def urgency_class(value, today: date | None = None) -> str:
    """CSS-Klasse nach Nähe des Datums."""
    days = days_until(value, today)
    if days is None:
        return ""
    if days < 0:
        return "overdue"
    if days <= 1:
        return "soon"
    if days <= 7:
        return "upcoming"
    return ""


def thread_status_label(status: str | None) -> str:
    return THREAD_STATUS_LABELS.get(status, status or "—")


def suggestion_status_label(status: str | None) -> str:
    return SUGGESTION_STATUS_LABELS.get(status, status or "—")


def event_range_text(thread: dict) -> str:
    """Ereigniszeitraum als Text, inkl. Originalangabe bei 'ca.'."""
    start = thread.get("event_start")
    end = thread.get("event_end")
    if not start:
        return ""
    if end and parse_date(end) != parse_date(start):
        text = f"{de_date(start)} – {de_date(end)}"
    else:
        text = de_date(start)
    if thread.get("time_precision") == "approximate":
        original = thread.get("time_text")
        if original:
            return f"ca. {text} („{original}“)"
        return f"ca. {text}"
    return text


# --- Kalenderaktionen ---


def action_type_label(action_type: str | None) -> str:
    return ACTION_TYPE_LABELS.get(action_type, action_type or "—")


def action_status_label(status: str | None) -> str:
    return ACTION_STATUS_LABELS.get(status, status or "—")


def event_time_text(value, all_day: bool = False) -> str:
    """'05.11.2026, 14:00 Uhr' bzw. '05.11.2026' (ganztägig)."""
    if value is None:
        return "—"
    if all_day:
        return de_date(value)
    return de_datetime(value)


def action_time_text(action: dict) -> str:
    """Zeitraum einer Aktion, z. B. '05.11.2026, 14:00 – 15:00 Uhr'."""
    payload = action.get("payload") or {}
    snapshot = action.get("snapshot") or {}
    all_day = bool(
        payload.get("all_day")
        if payload.get("all_day") is not None
        else snapshot.get("all_day")
    )
    start = payload.get("start") or snapshot.get("start")
    end = payload.get("end") or snapshot.get("end")
    if not start:
        return "—"
    if all_day:
        start_text = de_date(start)
        if end and parse_date(end) != parse_date(start):
            return f"{start_text} – {de_date(end)} (ganztägig)"
        return f"{start_text} (ganztägig)"
    start_dt = _parse_dt_berlin(start)
    end_dt = _parse_dt_berlin(end)
    if start_dt and end_dt and start_dt.date() == end_dt.date():
        return (
            f"{start_dt.strftime('%d.%m.%Y')}, "
            f"{start_dt.strftime('%H:%M')} – "
            f"{end_dt.strftime('%H:%M')} Uhr"
        )
    return f"{de_datetime(start)} – {de_datetime(end)}"


def _parse_dt_berlin(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(BERLIN)
    return dt


def action_changes(action: dict) -> list[str]:
    """Änderungsliste eines update-Vorschlags (deutsch)."""
    if action.get("action_type") != "update":
        return []
    snapshot = action.get("snapshot") or {}
    payload = action.get("payload") or {}
    return calendar_service.diff_event_fields(
        snapshot, payload, bool(snapshot.get("all_day"))
    )
