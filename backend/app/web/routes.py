"""Serverseitig gerenderte Weboberfläche für Hugo.

Nutzt dieselben Storage-/Service-Funktionen wie die
JSON-API; eigene Fachlogik gibt es hier nicht.
"""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.agent.evaluation import run_evaluation
from app.calendar import client as calendar_client
from app.calendar import execution as calendar_execution
from app.calendar import service as calendar_service
from app.chat_service import ConversationNotFoundError, run_chat
from app.storage.calendar_actions import (
    count_pending_actions,
    list_action_log,
    list_actions,
)
from app.storage.database import get_messages, list_conversations
from app.storage.suggestions import (
    count_open_suggestions,
    list_runs,
    list_suggestions,
    update_suggestion_status,
)
from app.storage.threads import get_thread, list_threads, validate_tag
from app.tools.dates import today_berlin
from app.web import formatting as fmt
from app.web.timeline import TimelineData, demo_timeline

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent

templates = Jinja2Templates(directory=WEB_DIR / "templates")
templates.env.filters["de_date"] = fmt.de_date
templates.env.filters["de_datetime"] = fmt.de_datetime

router = APIRouter(prefix="/ui", include_in_schema=False)

SUGGESTION_ACTIONS = ("confirmed", "deferred", "dismissed")

# Anzeigereihenfolge der Thread-Gruppen
THREAD_GROUPS = ("active", "waiting", "proposed", "completed", "archived")


def _nav(active: str, *, read_only: bool = False) -> dict:
    open_count = count_open_suggestions() if read_only else len(list_suggestions(status="open", limit=500))
    return {
        "nav_active": active,
        "nav_open_suggestions": open_count,
        "nav_pending_calendar_actions": count_pending_actions(),
    }


def _thread_titles(suggestions: list[dict]) -> dict:
    """Thread-Titel für die Vorschlagsdarstellung."""
    titles = {}
    for suggestion in suggestions:
        thread_id = suggestion.get("thread_id")
        if thread_id is not None and thread_id not in titles:
            thread = get_thread(thread_id)
            titles[thread_id] = (
                thread["title"] if thread else f"#{thread_id}"
            )
    return titles


def _error_page(request: Request, status_code: int, message: str):
    return templates.TemplateResponse(
        request,
        "error.html",
        {**_nav(""), "status_code": status_code, "message": message},
        status_code=status_code,
    )


def _safe_next(value: str | None) -> str:
    """Nur interne UI-Ziele zulassen (kein Open Redirect)."""
    if value and value.startswith("/ui/"):
        return value
    return "/ui/heute"


@router.get("/")
def ui_home():
    return RedirectResponse("/ui/heute", status_code=303)


# --- Chat ---


def _render_chat(
    request: Request,
    *,
    conversation_id: int | None,
    messages: list[dict] | None = None,
    draft: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            **_nav("chat"),
            "conversations": list_conversations(limit=50),
            "conversation_id": conversation_id,
            "messages": messages or [],
            "draft": draft,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/chat")
def chat_new(request: Request):
    return _render_chat(request, conversation_id=None)


@router.get("/chat/{conversation_id}")
def chat_show(request: Request, conversation_id: int):
    messages = get_messages(conversation_id)
    if not messages:
        return _error_page(
            request, 404, "Diese Unterhaltung wurde nicht gefunden."
        )
    return _render_chat(
        request, conversation_id=conversation_id, messages=messages
    )


@router.post("/chat")
def chat_send(
    request: Request,
    message: str = Form(""),
    conversation_id: str = Form(""),
):
    message = message.strip()
    try:
        conv_id = int(conversation_id) if conversation_id.strip() else None
    except ValueError:
        return _error_page(request, 400, "Ungültige Unterhaltungs-ID.")

    if not message:
        messages = get_messages(conv_id) if conv_id else []
        return _render_chat(
            request,
            conversation_id=conv_id,
            messages=messages,
            error="Bitte eine Nachricht eingeben.",
            status_code=400,
        )

    try:
        result = run_chat(message, conv_id)
    except ConversationNotFoundError:
        return _error_page(
            request, 404, "Diese Unterhaltung wurde nicht gefunden."
        )
    except Exception:
        logger.exception("Chat-Antwort fehlgeschlagen")
        messages = get_messages(conv_id) if conv_id else []
        return _render_chat(
            request,
            conversation_id=conv_id,
            messages=messages,
            draft=message,
            error=(
                "Hugo konnte gerade nicht antworten. "
                "Bitte später erneut versuchen."
            ),
            status_code=502,
        )

    return RedirectResponse(
        f"/ui/chat/{result['conversation_id']}", status_code=303
    )


# --- Heute ---


@router.get("/heute")
def heute(request: Request):
    open_suggestions = list_suggestions(
        status="open", limit=200, mark_surfaced=True
    )
    deferred = list_suggestions(status="deferred", limit=200)
    runs = list_runs(limit=1)
    today = today_berlin()
    return templates.TemplateResponse(
        request,
        "heute.html",
        {
            "nav_active": "heute",
            "nav_open_suggestions": len(open_suggestions),
            "today": today,
            "today_weekday": fmt.de_weekday(today),
            "open_suggestions": open_suggestions,
            "deferred_suggestions": deferred,
            "thread_titles": _thread_titles(open_suggestions + deferred),
            "last_run": runs[0] if runs else None,
            "fmt": fmt,
        },
    )


@router.post("/suggestions/{suggestion_id}")
def suggestion_action(
    request: Request,
    suggestion_id: int,
    action: str = Form(""),
    next: str = Form("/ui/heute"),
    deferred_until: str = Form(""),
):
    if action not in SUGGESTION_ACTIONS:
        return _error_page(
            request,
            400,
            "Ungültige Aktion. Erlaubt: bestätigen, "
            "zurückstellen, verwerfen.",
        )
    try:
        result = update_suggestion_status(
            suggestion_id, action, deferred_until=deferred_until or None,
        )
    except ValueError as exc:
        return _error_page(request, 400, str(exc))
    if result is None:
        return _error_page(
            request, 404, "Dieser Vorschlag wurde nicht gefunden."
        )
    return RedirectResponse(_safe_next(next), status_code=303)


@router.post("/evaluate")
def evaluate(request: Request):
    """Manueller Evaluationslauf, wie POST /proactivity/evaluate."""
    try:
        run_evaluation(trigger="manual")
    except Exception:
        logger.exception("Evaluationslauf fehlgeschlagen")
        return _error_page(
            request,
            502,
            "Die Auswertung ist fehlgeschlagen. "
            "Bitte später erneut versuchen.",
        )
    return RedirectResponse("/ui/heute", status_code=303)


# --- Vorhaben ---


@router.get("/zeitleiste")
def timeline(request: Request, demo: bool = False, size: str = "normal"):
    demo_enabled = os.getenv("HUGO_TIMELINE_DEMO", "false").lower() == "true"
    if demo and not demo_enabled:
        return templates.TemplateResponse(
            request, "error.html",
            {**_nav("threads", read_only=True), "status_code": 404,
             "message": "Die lokale Zeitleisten-Demo ist nicht aktiviert."},
            status_code=404,
        )
    data = demo_timeline(today_berlin()) if demo else TimelineData(demo=False, today=today_berlin())
    if demo and size == "large":
        data = demo_timeline(today_berlin(), large=True)
    return templates.TemplateResponse(
        request, "timeline.html",
        {**_nav("threads", read_only=True), "timeline": data,
         "demo_enabled": demo_enabled, "fmt": fmt},
    )


@router.get("/threads")
def threads(request: Request, tag: str | None = None):
    tag = tag or None
    try:
        validate_tag(tag)
    except ValueError as exc:
        return _error_page(request, 400, str(exc))
    all_threads = list_threads(limit=500, tag=tag)
    groups = [
        (status, [t for t in all_threads if t["status"] == status])
        for status in THREAD_GROUPS
    ]
    groups = [(status, items) for status, items in groups if items]
    return templates.TemplateResponse(
        request,
        "threads.html",
        {
            **_nav("threads"),
            "groups": groups,
            "selected_tag": tag,
            "fmt": fmt,
        },
    )


@router.get("/threads/{thread_id}")
def thread_detail(request: Request, thread_id: int):
    thread = get_thread(thread_id)
    if thread is None:
        return _error_page(
            request, 404, "Dieses Vorhaben wurde nicht gefunden."
        )
    related = [
        s
        for s in list_suggestions(limit=500)
        if s["thread_id"] == thread_id
    ]
    return templates.TemplateResponse(
        request,
        "thread_detail.html",
        {
            **_nav("threads"),
            "thread": thread,
            "suggestions": related,
            "fmt": fmt,
        },
    )


# --- Kalender ---

CALENDAR_ACTION_FORM_ACTIONS = ("confirm", "reject")

# Kurze Rückmeldungen nach Aktionsausführung (Query-Parameter).
_CALENDAR_FLASHES = {
    "ausgefuehrt": "Die Aktion wurde ausgeführt.",
    "abgelehnt": "Die Aktion wurde abgelehnt.",
    "konflikt": (
        "Der Termin wurde seit dem Vorschlag verändert. "
        "Bitte prüfe den aktuellen Stand und bestätige erneut."
    ),
    "fehler": "Die Ausführung ist fehlgeschlagen.",
    "verbunden": "Das Google-Konto ist jetzt verbunden.",
    "getrennt": "Die Google-Verbindung wurde getrennt.",
}


def _render_kalender(
    request: Request,
    *,
    flash: str | None = None,
    status_code: int = 200,
):
    connected = calendar_client.is_connected()
    calendars = None
    connection_error = None
    if connected:
        try:
            calendars = calendar_client.list_calendars()
        except calendar_client.CalendarError as exc:
            connection_error = str(exc)
    open_actions = [
        a
        for a in list_actions(limit=200)
        if a["status"] in ("pending", "conflict")
    ]
    recent_actions = [
        a
        for a in list_actions(limit=200)
        if a["status"] not in ("pending", "conflict")
    ][:10]
    return templates.TemplateResponse(
        request,
        "kalender.html",
        {
            **_nav("kalender"),
            "configured": calendar_client.is_configured(),
            "connected": connected,
            "calendars": calendars,
            "calendar_names": {
                c["id"]: c["summary"] for c in calendars or []
            },
            "connection_error": connection_error,
            "open_actions": open_actions,
            "recent_actions": recent_actions,
            "action_log": list_action_log(limit=10),
            "flash": _CALENDAR_FLASHES.get(flash),
            "flash_is_error": flash in ("fehler", "konflikt"),
            "fmt": fmt,
            "cal": calendar_service,
        },
        status_code=status_code,
    )


@router.get("/kalender")
def kalender(request: Request, hinweis: str | None = None):
    return _render_kalender(request, flash=hinweis)


@router.get("/kalender/auth/start")
def kalender_auth_start(request: Request):
    """Leitet zu Googles OAuth-Consent-Screen weiter."""
    if not calendar_client.is_configured():
        return _error_page(
            request,
            400,
            "Google-OAuth ist nicht konfiguriert "
            "(GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET fehlen).",
        )
    try:
        url = calendar_client.build_auth_url(
            calendar_client.new_oauth_state()
        )
    except calendar_client.CalendarError as exc:
        return _error_page(request, 502, str(exc))
    return RedirectResponse(url, status_code=303)


@router.get("/kalender/auth/callback")
def kalender_auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """OAuth-Rücksprung: Code gegen Tokens tauschen."""
    if error:
        return _error_page(
            request,
            400,
            f"Die Google-Anmeldung wurde abgebrochen ({error}).",
        )
    if not code or not state:
        return _error_page(
            request, 400, "Unvollständige OAuth-Antwort."
        )
    try:
        calendar_client.exchange_code(code, state)
    except calendar_client.CalendarError as exc:
        logger.warning("OAuth-Callback fehlgeschlagen: %s", exc)
        return _error_page(
            request,
            502,
            "Die Verbindung mit Google konnte nicht "
            "hergestellt werden.",
        )
    return RedirectResponse(
        "/ui/kalender?hinweis=verbunden", status_code=303
    )


@router.post("/kalender/disconnect")
def kalender_disconnect(request: Request):
    calendar_client.disconnect()
    return RedirectResponse(
        "/ui/kalender?hinweis=getrennt", status_code=303
    )


@router.post("/calendar-actions/{action_id}")
def calendar_action(
    request: Request,
    action_id: int,
    action: str = Form(""),
    force: str = Form(""),
    next: str = Form("/ui/kalender"),
):
    """Bestätigen oder Ablehnen einer ausstehenden Aktion.

    Einziger UI-Auslöser für schreibende Kalenderoperationen.
    """
    if action not in CALENDAR_ACTION_FORM_ACTIONS:
        return _error_page(
            request, 400, "Ungültige Aktion. Erlaubt: bestätigen, ablehnen."
        )
    target = _safe_next_calendar(next)
    try:
        if action == "reject":
            calendar_execution.reject_action(action_id)
            flash = "abgelehnt"
        else:
            calendar_execution.confirm_action(
                action_id, force=force == "1"
            )
            flash = "ausgefuehrt"
    except calendar_execution.ActionNotFoundError:
        return _error_page(
            request, 404, "Diese Kalenderaktion wurde nicht gefunden."
        )
    except calendar_execution.ActionAlreadyHandledError:
        return _error_page(
            request,
            409,
            "Diese Aktion wurde bereits behandelt.",
        )
    except calendar_execution.ActionConflictError:
        flash = "konflikt"
    except calendar_client.CalendarError:
        logger.exception("Kalenderaktion %s fehlgeschlagen", action_id)
        flash = "fehler"
    return RedirectResponse(
        f"{target}?hinweis={flash}", status_code=303
    )


def _safe_next_calendar(value: str | None) -> str:
    """Nur interne UI-Ziele zulassen (kein Open Redirect)."""
    if value and value.startswith("/ui/"):
        # Bestehende Query-Parameter entfernen, damit der
        # Hinweis nicht vermischt wird.
        return value.split("?")[0]
    return "/ui/kalender"
