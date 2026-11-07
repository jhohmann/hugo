"""Bestätigungs- und Ausführungspfad für Kalenderaktionen.

Trennung der Verantwortlichkeiten:
- Der Agent erzeugt über propose_* nur ausstehende Aktionen.
- Erst confirm_action (ausschließlich ausgelöst über die
  Weboberfläche/API) führt den Google-API-Aufruf aus.
- Statusübergänge sind in der Datenbank gegen doppelte
  Ausführung abgesichert.
"""

import logging
from datetime import date, datetime, time, timedelta

from app.calendar import client, service
from app.storage import calendar_actions as store
from app.tools.dates import BERLIN, today_berlin

logger = logging.getLogger(__name__)

_EDITABLE_FIELDS = (
    "summary", "description", "location", "start", "end", "all_day",
)


class ActionNotFoundError(Exception):
    """Aktions-ID unbekannt."""


class ActionAlreadyHandledError(Exception):
    """Aktion wurde bereits bestätigt, abgelehnt oder ausgeführt."""


class ActionConflictError(Exception):
    """Der Termin wurde seit dem Vorschlag verändert."""

    def __init__(self, action: dict):
        super().__init__("Termin-Konflikt")
        self.action = action


# --- Lesende Zugriffe (für Agenten-Werkzeuge und UI) ---


def get_calendars() -> list[dict]:
    return client.list_calendars()


def get_events(
    time_min: datetime,
    time_max: datetime,
    calendar_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Termine aller (oder eines) Kalender, zusammengeführt
    und nach Beginn sortiert."""
    if calendar_id:
        calendars = [{"id": calendar_id}]
    else:
        calendars = client.list_calendars()
    events = []
    for calendar in calendars:
        events.extend(
            service.event_to_tool_dict(event, calendar["id"])
            for event in client.list_events(
                calendar["id"], time_min, time_max, max_results=limit
            )
        )
    events.sort(key=lambda e: e["start"] or "")
    return events[:limit]


def search_events(
    query: str,
    calendar_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Termine im aktuellen und folgenden Kalenderjahr live durchsuchen."""
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError("Suchbegriff muss 1 bis 200 Zeichen enthalten.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit muss zwischen 1 und 100 liegen.")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset muss eine nichtnegative ganze Zahl sein.")
    query = query.strip()
    year = today_berlin().year
    time_min = datetime(year, 1, 1, tzinfo=BERLIN)
    time_max = datetime(year + 2, 1, 1, tzinfo=BERLIN)
    calendars = client.list_calendars()
    if calendar_id:
        calendars = [c for c in calendars if c["id"] == calendar_id]
        if not calendars:
            raise ValueError("Kalender nicht gefunden. Zuerst list_calendars verwenden.")
    events = []
    searched = []
    unsearchable = []
    for calendar in calendars:
        if calendar.get("access_role") == "freeBusyReader":
            unsearchable.append(calendar["id"])
            continue
        events.extend(
            service.event_to_tool_dict(event, calendar["id"])
            for event in client.search_events(
                calendar["id"], time_min, time_max, query
            )
        )
        searched.append(calendar["id"])

    def sort_key(event):
        start = datetime.fromisoformat(event["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=BERLIN)
        return start.timestamp(), event["calendar_id"], event["event_id"]

    events.sort(key=sort_key)
    page = events[offset:offset + limit]
    has_more = offset + len(page) < len(events)
    return {
        "query": query,
        "time_min": time_min.isoformat(),
        "time_max": time_max.isoformat(),
        "timezone": "Europe/Berlin",
        "searched_calendars": searched,
        "unsearchable_calendars": unsearchable,
        "events": page,
        "total_count": len(events),
        "has_more": has_more,
        "next_offset": offset + len(page) if has_more else None,
    }


def find_free_slots(
    day_from: date,
    day_to: date,
    duration_minutes: int = 60,
    day_start: time = time(8, 0),
    day_end: time = time(20, 0),
    calendar_id: str | None = None,
) -> list[dict]:
    """Freie Zeitfenster über alle Kalender hinweg."""
    if calendar_id:
        calendars = [{"id": calendar_id}]
    else:
        calendars = client.list_calendars()
    events = []
    time_min = datetime.combine(day_from, time.min, tzinfo=BERLIN)
    time_max = datetime.combine(
        day_to + timedelta(days=1), time.min, tzinfo=BERLIN
    )
    for calendar in calendars:
        events.extend(
            client.list_events(calendar["id"], time_min, time_max)
        )
    return service.compute_free_slots(
        events, day_from, day_to, duration_minutes, day_start, day_end
    )


# --- Vorschläge (Agenten-Werkzeuge, keine API-Schreibzugriffe) ---


def _validate_writable_calendar(calendar_id: str) -> dict:
    for calendar in client.list_calendars():
        if calendar["id"] == calendar_id:
            if not calendar["writable"]:
                raise client.CalendarError(
                    f"Keine Schreibberechtigung für Kalender "
                    f"'{calendar['summary']}'."
                )
            return calendar
    raise client.CalendarError(
        f"Kalender '{calendar_id}' nicht gefunden."
    )


def _parse_time_value(value: str, all_day: bool):
    try:
        if all_day:
            return date.fromisoformat(str(value)[:10])
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"Ungültiges Zeitformat: {value!r}. ISO 8601 erwartet."
        )


def _validate_payload(payload: dict, require_times: bool) -> dict:
    """Validiert und normalisiert vorgeschlagene Felder."""
    cleaned = {
        key: payload.get(key)
        for key in _EDITABLE_FIELDS
        if payload.get(key) is not None
    }
    all_day = bool(cleaned.get("all_day"))
    if require_times:
        if not cleaned.get("summary"):
            raise ValueError("Ein Titel (summary) ist erforderlich.")
        if not cleaned.get("start") or not cleaned.get("end"):
            raise ValueError("Beginn und Ende sind erforderlich.")
    if cleaned.get("start") is not None:
        cleaned["start"] = _parse_time_value(
            cleaned["start"], all_day
        ).isoformat()
    if cleaned.get("end") is not None:
        cleaned["end"] = _parse_time_value(
            cleaned["end"], all_day
        ).isoformat()
    if (
        cleaned.get("start") is not None
        and cleaned.get("end") is not None
        and cleaned["end"] <= cleaned["start"]
    ):
        raise ValueError("Das Ende liegt nicht nach dem Beginn.")
    if not cleaned:
        raise ValueError("Keine zu ändernden Felder übergeben.")
    return cleaned


def propose_create(
    calendar_id: str,
    payload: dict,
    source_message_id: int | None = None,
) -> dict:
    """Ausstehende Aktion 'Termin anlegen'."""
    _validate_writable_calendar(calendar_id)
    cleaned = _validate_payload(payload, require_times=True)
    action_id = store.create_action(
        "create",
        calendar_id,
        cleaned,
        source_message_id=source_message_id,
    )
    logger.info("Kalenderaktion %s (create) vorgeschlagen", action_id)
    return store.get_action(action_id)


def propose_update(
    calendar_id: str,
    event_id: str,
    changes: dict,
    source_message_id: int | None = None,
) -> dict:
    """Ausstehende Aktion 'Termin ändern' mit Snapshot."""
    _validate_writable_calendar(calendar_id)
    event = client.get_event(calendar_id, event_id)
    cleaned = _validate_payload(changes, require_times=False)
    snapshot = service.snapshot_from_event(event)
    action_id = store.create_action(
        "update",
        calendar_id,
        cleaned,
        event_id=event_id,
        snapshot=snapshot,
        source_message_id=source_message_id,
    )
    logger.info("Kalenderaktion %s (update) vorgeschlagen", action_id)
    return store.get_action(action_id)


def propose_delete(
    calendar_id: str,
    event_id: str,
    source_message_id: int | None = None,
) -> dict:
    """Ausstehende Aktion 'Termin löschen' mit Snapshot."""
    _validate_writable_calendar(calendar_id)
    event = client.get_event(calendar_id, event_id)
    snapshot = service.snapshot_from_event(event)
    action_id = store.create_action(
        "delete",
        calendar_id,
        {"summary": snapshot["summary"]},
        event_id=event_id,
        snapshot=snapshot,
        source_message_id=source_message_id,
    )
    logger.info("Kalenderaktion %s (delete) vorgeschlagen", action_id)
    return store.get_action(action_id)


# --- Bestätigung und Ausführung (nur via UI/API) ---


def _has_changed_since_proposal(event: dict, snapshot: dict) -> bool:
    """Konflikterkennung über etag/updated."""
    return (
        event.get("etag") != snapshot.get("etag")
        or event.get("updated") != snapshot.get("updated")
    )


def _execute_create(action: dict) -> dict:
    payload = action["payload"]
    body = service.payload_to_body(payload)
    body["summary"] = service.ensure_suffix(payload["summary"])
    body["description"] = service.append_changelog(
        payload.get("description"), "Erstellt durch Hugo"
    )
    body["id"] = service.deterministic_event_id(action["id"])
    try:
        event = client.insert_event(action["calendar_id"], body)
        note = None
    except client.GoogleApiError as exc:
        if exc.status_code != 409:
            raise
        # Dieselbe Aktion wurde bereits ausgeführt (z. B. nach
        # einem Timeout): kein zweites Mal anlegen.
        event = client.get_event(
            action["calendar_id"], body["id"]
        )
        note = "already_existed"
    result = {"event": service.event_to_tool_dict(
        event, action["calendar_id"]
    )}
    if note:
        result["note"] = note
    return result


def _execute_update(action: dict) -> dict:
    payload = action["payload"]
    snapshot = action["snapshot"]
    all_day = bool(snapshot.get("all_day"))
    changes = service.diff_event_fields(snapshot, payload, all_day)
    if not changes:
        return {"note": "no_changes"}
    body = service.payload_to_body(payload, all_day=all_day)
    if payload.get("summary") is not None:
        body["summary"] = service.ensure_suffix(payload["summary"])
    base_description = (
        payload["description"]
        if payload.get("description") is not None
        else snapshot.get("description")
    )
    body["description"] = service.append_changelog(
        base_description, "; ".join(changes)
    )
    event = client.patch_event(
        action["calendar_id"], action["event_id"], body
    )
    return {
        "event": service.event_to_tool_dict(
            event, action["calendar_id"]
        ),
        "changes": changes,
    }


def _execute_delete(action: dict) -> dict:
    client.delete_event(action["calendar_id"], action["event_id"])
    return {"deleted": True}


def confirm_action(action_id: int, force: bool = False) -> dict:
    """Bestätigt eine ausstehende Aktion und führt sie aus.

    force=True ist nur nach einer Konfliktprüfung zulässig
    (erneute Bestätigung durch den Nutzer).
    """
    action = store.get_action(action_id)
    if action is None:
        raise ActionNotFoundError(f"Aktion {action_id} unbekannt.")
    if action["status"] not in store.CONFIRMABLE_STATUSES:
        raise ActionAlreadyHandledError(
            f"Aktion {action_id} hat bereits den Status "
            f"'{action['status']}'."
        )
    if action["status"] == "conflict" and not force:
        raise ActionConflictError(action)
    # Atomarer Übergang: schlägt fehl, wenn parallel bereits
    # bestätigt/abgelehnt wurde.
    if not store.try_mark_confirmed(action_id):
        raise ActionAlreadyHandledError(
            f"Aktion {action_id} wurde bereits behandelt."
        )

    try:
        if action["action_type"] in ("update", "delete"):
            try:
                current = client.get_event(
                    action["calendar_id"], action["event_id"]
                )
            except client.EventNotFoundError:
                raise client.CalendarError(
                    "Der Termin existiert nicht mehr."
                )
            if not force and _has_changed_since_proposal(
                current, action["snapshot"]
            ):
                store.mark_conflict(
                    action_id,
                    service.event_to_tool_dict(
                        current, action["calendar_id"]
                    ),
                )
                logger.info(
                    "Kalenderaktion %s: Konflikt erkannt", action_id
                )
                raise ActionConflictError(store.get_action(action_id))
            if force:
                # Erneute Bestätigung nach Konflikt: das Diff und
                # der Changelog beziehen sich auf den aktuellen
                # Stand, nicht auf den veralteten Vorschlag.
                action["snapshot"] = service.snapshot_from_event(
                    current
                )

        if action["action_type"] == "create":
            result = _execute_create(action)
        elif action["action_type"] == "update":
            result = _execute_update(action)
        else:
            result = _execute_delete(action)

        store.mark_executed(action_id, result)
        store.log_action(
            action_id,
            action["action_type"],
            action["calendar_id"],
            action["event_id"],
            action["payload"].get("summary"),
            detail={
                "result": result,
                # Bei Löschungen den letzten bekannten Stand
                # sichern, da die Beschreibung danach weg ist.
                "snapshot": action["snapshot"],
            },
        )
        logger.info(
            "Kalenderaktion %s (%s) ausgeführt",
            action_id,
            action["action_type"],
        )
        return store.get_action(action_id)

    except ActionConflictError:
        raise
    except Exception as exc:
        logger.exception(
            "Kalenderaktion %s fehlgeschlagen", action_id
        )
        store.mark_failed(action_id, str(exc))
        store.log_action(
            action_id,
            action["action_type"],
            action["calendar_id"],
            action["event_id"],
            action["payload"].get("summary"),
            detail={"error": str(exc)},
        )
        raise


def reject_action(action_id: int) -> dict:
    """Lehnt eine ausstehende Aktion ab."""
    action = store.get_action(action_id)
    if action is None:
        raise ActionNotFoundError(f"Aktion {action_id} unbekannt.")
    if not store.try_mark_rejected(action_id):
        raise ActionAlreadyHandledError(
            f"Aktion {action_id} hat bereits den Status "
            f"'{action['status']}'."
        )
    store.log_action(
        action_id,
        action["action_type"],
        action["calendar_id"],
        action["event_id"],
        action["payload"].get("summary"),
        detail={"rejected": True},
    )
    logger.info("Kalenderaktion %s abgelehnt", action_id)
    return store.get_action(action_id)
