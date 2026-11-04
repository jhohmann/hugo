"""Fachlogik der Kalenderintegration (rein, ohne I/O).

- Kennzeichnung von Hugo-Terminen mit dem Suffix " [H]"
- Änderungsverlauf (Changelog) in der Terminbeschreibung
- Feld-Diff für Änderungsprotokoll und Konfliktanzeige
- Berechnung freier Zeitfenster
- Umwandlung zwischen Google-Event-Format und Hugos
  Nutzdarstellung (inkl. ganztägiger Termine mit exklusivem
  Enddatum bei Google)
"""

import re
from datetime import date, datetime, time, timedelta

from app.tools.dates import BERLIN

HUGO_SUFFIX = " [H]"
CHANGELOG_MARKER = "--- Hugo Changelog ---"

# Erlaubter Zeichensatz für Google-Event-IDs: base32hex
# (Kleinbuchstaben a-v und Ziffern 0-9), 5-1024 Zeichen.
_EVENT_ID_PREFIX = "hugo"

MAX_DESCRIPTION_FOR_TOOL = 500


# --- [H]-Suffix und Changelog ---


def ensure_suffix(title: str | None) -> str:
    """Titel mit ' [H]' kennzeichnen, ohne zu duplizieren."""
    title = (title or "").strip()
    if re.search(r"\[H\]\s*$", title):
        return title
    return f"{title}{HUGO_SUFFIX}"


def is_hugo_managed(title: str | None) -> bool:
    return bool(title) and bool(re.search(r"\[H\]\s*$", title))


def changelog_timestamp(now: datetime | None = None) -> str:
    """'2026-11-04 15:30 Europe/Berlin' für Changelog-Einträge."""
    now = now or datetime.now(BERLIN)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BERLIN)
    now = now.astimezone(BERLIN)
    return now.strftime("%Y-%m-%d %H:%M") + " Europe/Berlin"


def append_changelog(
    description: str | None,
    entry: str,
    now: datetime | None = None,
) -> str:
    """Hängt einen Eintrag an den Hugo-Changelog an.

    Bestehender Beschreibungstext und vorhandene
    Changelog-Einträge bleiben erhalten.
    """
    line = f"{changelog_timestamp(now)} | {entry}"
    text = (description or "").rstrip()
    if CHANGELOG_MARKER in text:
        return f"{text}\n{line}"
    if text:
        return f"{text}\n\n{CHANGELOG_MARKER}\n{line}"
    return f"{CHANGELOG_MARKER}\n{line}"


# --- Feld-Diff für Änderungsprotokoll und Konfliktanzeige ---


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt_change_value(value, all_day: bool) -> str:
    """Kurze Darstellung eines Zeitwerts für das Protokoll."""
    if value is None:
        return "—"
    if all_day:
        d = _parse_dt(value) or value
        if isinstance(d, datetime):
            return d.strftime("%d.%m.%Y")
        return str(d)[:10]
    dt = _parse_dt(value)
    if dt is None:
        return str(value)
    return dt.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M")


def _fmt_time_pair(old, new, all_day: bool) -> str:
    """'14:00 → 15:00' am selben Tag, sonst mit Datum."""
    old_dt, new_dt = _parse_dt(old), _parse_dt(new)
    if not all_day and old_dt and new_dt:
        old_b = old_dt.astimezone(BERLIN)
        new_b = new_dt.astimezone(BERLIN)
        if old_b.date() == new_b.date():
            return (
                f"{old_b.strftime('%H:%M')} → {new_b.strftime('%H:%M')}"
            )
    return (
        f"{_fmt_change_value(old, all_day)} → "
        f"{_fmt_change_value(new, all_day)}"
    )


def diff_event_fields(
    snapshot: dict, payload: dict, all_day: bool = False
) -> list[str]:
    """Mensch lesbare Änderungsliste (deutsch).

    Verglichen werden nur die im payload tatsächlich
    gesetzten Felder gegen den Snapshot.
    """
    changes = []
    if payload.get("summary") is not None:
        old = snapshot.get("summary") or ""
        if payload["summary"] != old:
            changes.append(
                f"Titel geändert: „{old}“ → „{payload['summary']}“"
            )
    if payload.get("start") is not None:
        old = snapshot.get("start")
        if _parse_dt(payload["start"]) != _parse_dt(old):
            changes.append(
                "Beginn geändert: "
                + _fmt_time_pair(old, payload["start"], all_day)
            )
    if payload.get("end") is not None:
        old = snapshot.get("end")
        if _parse_dt(payload["end"]) != _parse_dt(old):
            changes.append(
                "Ende geändert: "
                + _fmt_time_pair(old, payload["end"], all_day)
            )
    if payload.get("location") is not None:
        old = snapshot.get("location") or ""
        if payload["location"] != old:
            if not old:
                changes.append(
                    f"Ort ergänzt: „{payload['location']}“"
                )
            elif not payload["location"]:
                changes.append(f"Ort entfernt: „{old}“")
            else:
                changes.append(
                    f"Ort geändert: „{old}“ → „{payload['location']}“"
                )
    if payload.get("description") is not None:
        old = snapshot.get("description") or ""
        if payload["description"] != old:
            changes.append("Beschreibung geändert")
    return changes


# --- Google-Event-Format ↔ Hugo-Darstellung ---


def parse_event_time(value: dict | None) -> tuple[datetime | date | None, bool]:
    """Google-{date|dateTime} → (Wert, all_day)."""
    if not value:
        return None, False
    if "date" in value:
        return date.fromisoformat(value["date"]), True
    if "dateTime" in value:
        return datetime.fromisoformat(
            value["dateTime"].replace("Z", "+00:00")
        ), False
    return None, False


def event_to_tool_dict(event: dict, calendar_id: str) -> dict:
    """Kompakte, modellfreundliche Darstellung eines Termins.

    Enthält niemals Zugangsdaten. Ganztägige Termine werden
    mit inklusivem Enddatum ausgegeben (Google speichert das
    Enddatum exklusiv).
    """
    start, all_day = parse_event_time(event.get("start"))
    end, _ = parse_event_time(event.get("end"))
    if all_day and isinstance(end, date):
        end = end - timedelta(days=1)
    description = event.get("description") or ""
    if len(description) > MAX_DESCRIPTION_FOR_TOOL:
        description = description[:MAX_DESCRIPTION_FOR_TOOL] + "…"
    return {
        "calendar_id": calendar_id,
        "event_id": event.get("id"),
        "title": event.get("summary", "(ohne Titel)"),
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "all_day": all_day,
        "location": event.get("location"),
        "description": description or None,
        "hugo_managed": is_hugo_managed(event.get("summary")),
        "updated": event.get("updated"),
    }


def snapshot_from_event(event: dict) -> dict:
    """Zustand zum Vorschlagszeitpunkt für Konflikterkennung
    und Änderungsprotokoll."""
    start, all_day = parse_event_time(event.get("start"))
    end, _ = parse_event_time(event.get("end"))
    if all_day and isinstance(end, date):
        end = end - timedelta(days=1)
    return {
        "etag": event.get("etag"),
        "updated": event.get("updated"),
        "summary": event.get("summary", ""),
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "all_day": all_day,
        "description": event.get("description") or "",
        "location": event.get("location") or "",
    }


def deterministic_event_id(action_id: int) -> str:
    """Stabile Event-ID pro Aktion: verhindert unbemerkt
    doppelte Termine bei Timeout/Wiederholung (Google lehnt
    eine zweite Anlage mit derselben ID mit 409 ab)."""
    return f"{_EVENT_ID_PREFIX}{action_id:024x}"


def payload_to_body(payload: dict, all_day: bool | None = None) -> dict:
    """Google-Event-Body aus den vorgeschlagenen Feldern.

    Ganztägige Termine: das inklusive Enddatum des Payloads
    wird in Googles exklusives Enddatum umgerechnet. all_day
    kann übergeben werden, wenn das Payload es nicht enthält
    (z. B. bei Änderungen, Snapshot als Referenz).
    """
    body = {}
    if payload.get("summary") is not None:
        body["summary"] = payload["summary"]
    if payload.get("description") is not None:
        body["description"] = payload["description"]
    if payload.get("location") is not None:
        body["location"] = payload["location"]
    if all_day is None:
        all_day = bool(payload.get("all_day"))
    if payload.get("start") is not None:
        if all_day:
            body["start"] = {"date": str(payload["start"])[:10]}
        else:
            body["start"] = {
                "dateTime": payload["start"],
                "timeZone": "Europe/Berlin",
            }
    if payload.get("end") is not None:
        if all_day:
            end_date = date.fromisoformat(str(payload["end"])[:10])
            body["end"] = {
                "date": (end_date + timedelta(days=1)).isoformat()
            }
        else:
            body["end"] = {
                "dateTime": payload["end"],
                "timeZone": "Europe/Berlin",
            }
    return body


# --- Freie Zeitfenster ---


def busy_intervals(events: list[dict]) -> list[tuple[datetime, datetime]]:
    """Belegte Intervalle aus Google-Events (Europe/Berlin).

    'transparente' Termine (als 'verfügbar' markiert) blocken
    nicht. Ganztägige Termine blocken ihren gesamten Tag.
    """
    intervals = []
    for event in events:
        if event.get("transparency") == "transparent":
            continue
        start, all_day = parse_event_time(event.get("start"))
        end, _ = parse_event_time(event.get("end"))
        if start is None or end is None:
            continue
        if all_day:
            start = datetime.combine(start, time.min, tzinfo=BERLIN)
            end = datetime.combine(end, time.min, tzinfo=BERLIN)
        else:
            start = start.astimezone(BERLIN)
            end = end.astimezone(BERLIN)
        if end > start:
            intervals.append((start, end))
    intervals.sort()
    return intervals


def compute_free_slots(
    events: list[dict],
    day_from: date,
    day_to: date,
    duration_minutes: int = 60,
    day_start: time = time(8, 0),
    day_end: time = time(20, 0),
) -> list[dict]:
    """Freie Fenster je Tag zwischen day_start und day_end.

    Liefert [{'start': iso, 'end': iso, 'minutes': n}],
    nur Fenster mit mindestens duration_minutes Länge.
    """
    busy = busy_intervals(events)
    slots = []
    day = day_from
    while day <= day_to:
        window_start = datetime.combine(day, day_start, tzinfo=BERLIN)
        window_end = datetime.combine(day, day_end, tzinfo=BERLIN)
        cursor = window_start
        for start, end in busy:
            if end <= window_start or start >= window_end:
                continue
            if start > cursor:
                gap = (start - cursor).total_seconds() / 60
                if gap >= duration_minutes:
                    slots.append({
                        "start": cursor.isoformat(),
                        "end": start.isoformat(),
                        "minutes": int(gap),
                    })
            cursor = max(cursor, end)
            if cursor >= window_end:
                break
        if cursor < window_end:
            gap = (window_end - cursor).total_seconds() / 60
            if gap >= duration_minutes:
                slots.append({
                    "start": cursor.isoformat(),
                    "end": window_end.isoformat(),
                    "minutes": int(gap),
                })
        day += timedelta(days=1)
    return slots
