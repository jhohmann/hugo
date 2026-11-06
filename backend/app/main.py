
import logging
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent.evaluation import run_evaluation
from app.auth import AuthenticationMiddleware, router as auth_router
from app.calendar import client as calendar_client
from app.calendar import execution as calendar_execution
from app.chat_service import ConversationNotFoundError, run_chat
from app.storage.calendar_actions import (
    ACTION_STATUSES,
    list_actions,
)
from app.storage.memory_search import list_memories
from app.storage.suggestions import (
    DELIVERY_STATUSES,
    SUGGESTION_STATUSES,
    list_runs,
    list_suggestions,
    update_suggestion_status,
)
from app.storage.threads import THREAD_STATUSES, list_threads, validate_tag
from app.storage.database import (
    get_messages,
    list_conversations,
)
from app.web.routes import WEB_DIR, router as web_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Hugo", version="0.4.0")
app.add_middleware(AuthenticationMiddleware)
app.include_router(auth_router)

app.include_router(web_router)
app.mount(
    "/static",
    StaticFiles(directory=WEB_DIR / "static"),
    name="static",
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: int | None = None


class SuggestionPatch(BaseModel):
    status: str = Field(min_length=1)
    deferred_until: date | None = None


@app.get("/")
def root():
    return {
        "name": "Hugo",
        "version": "0.4.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        return run_chat(request.message, request.conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or empty",
        )


@app.get("/conversations")
def get_conversations(limit: int = 50):
    """Jüngste Unterhaltungen mit Vorschau (nur lesend)."""
    limit = max(1, min(limit, 500))
    return {"conversations": list_conversations(limit)}

@app.get("/memories")
def get_memories(limit: int = 100):
    limit = max(1, min(limit, 500))
    return {"memories": list_memories(limit)}


@app.get("/threads")
def get_threads(status: str | None = None, limit: int = 100, tag: str | None = None):
    try:
        validate_tag(tag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if status is not None and status not in THREAD_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid status: {status}. "
                f"Allowed: {', '.join(THREAD_STATUSES)}"
            ),
        )
    limit = max(1, min(limit, 500))
    return {"threads": list_threads(status=status, limit=limit, tag=tag)}


@app.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: int):
    messages = get_messages(conversation_id)

    if not messages:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or empty",
        )

    return messages


@app.post("/proactivity/evaluate")
def evaluate_proactivity():
    """Manuell ausgelöster Evaluationslauf über den Bestand."""
    return run_evaluation(trigger="manual")


@app.get("/proactivity/runs")
def get_runs(limit: int = 50):
    """Kontrolle: bisherige Evaluationsläufe."""
    limit = max(1, min(limit, 500))
    return {"runs": list_runs(limit)}


@app.get("/suggestions")
def get_suggestions(
    status: str | None = None,
    delivery: str | None = None,
    limit: int = 100,
):
    """Listet Vorschläge; Zurückgegebene gelten als zugestellt."""
    if status is not None and status not in SUGGESTION_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid status: {status}. "
                f"Allowed: {', '.join(SUGGESTION_STATUSES)}"
            ),
        )
    if delivery is not None and delivery not in DELIVERY_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid delivery: {delivery}. "
                f"Allowed: {', '.join(DELIVERY_STATUSES)}"
            ),
        )
    limit = max(1, min(limit, 500))
    return {
        "suggestions": list_suggestions(
            status=status,
            delivery=delivery,
            limit=limit,
            mark_surfaced=True,
        )
    }


@app.patch("/suggestions/{suggestion_id}")
def patch_suggestion(suggestion_id: int, patch: SuggestionPatch):
    """Vorschlag bestätigen, zurückstellen oder verwerfen."""
    if patch.status not in ("confirmed", "deferred", "dismissed"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid status: {patch.status}. "
                "Allowed: confirmed, deferred, dismissed"
            ),
        )
    try:
        result = update_suggestion_status(
            suggestion_id, patch.status, deferred_until=patch.deferred_until,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Suggestion not found",
        )
    return result


# --- Google Calendar ---


@app.get("/calendar/status")
def calendar_status():
    """Verbindungsstatus des Google-Kontos (ohne Tokens)."""
    credentials_connected = calendar_client.is_connected()
    status = {
        "configured": calendar_client.is_configured(),
        "connected": credentials_connected,
    }
    if credentials_connected:
        try:
            status["calendars"] = calendar_client.list_calendars()
        except calendar_client.CalendarError as exc:
            status["error"] = str(exc)
    return status


@app.get("/calendar/actions")
def calendar_actions(status: str | None = None, limit: int = 100):
    """Ausstehende und vergangene Kalenderaktionen."""
    if status is not None and status not in ACTION_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid status: {status}. "
                f"Allowed: {', '.join(ACTION_STATUSES)}"
            ),
        )
    limit = max(1, min(limit, 500))
    return {"actions": list_actions(status=status, limit=limit)}


def _run_confirmed_action(action_id: int, force: bool):
    try:
        return calendar_execution.confirm_action(action_id, force=force)
    except calendar_execution.ActionNotFoundError:
        raise HTTPException(
            status_code=404, detail="Calendar action not found"
        )
    except calendar_execution.ActionAlreadyHandledError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except calendar_execution.ActionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "conflict",
                "message": (
                    "Der Termin wurde seit dem Vorschlag "
                    "verändert. Erneute Bestätigung erforderlich."
                ),
                "action": exc.action,
            },
        )
    except calendar_client.CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/calendar/actions/{action_id}/confirm")
def calendar_action_confirm(action_id: int, force: bool = False):
    """Bestätigt eine ausstehende Aktion und führt sie aus.

    Einziger Ausführungspfad für schreibende
    Google-Calendar-Operationen.
    """
    return _run_confirmed_action(action_id, force)


@app.post("/calendar/actions/{action_id}/reject")
def calendar_action_reject(action_id: int):
    """Lehnt eine ausstehende Aktion ab."""
    try:
        return calendar_execution.reject_action(action_id)
    except calendar_execution.ActionNotFoundError:
        raise HTTPException(
            status_code=404, detail="Calendar action not found"
        )
    except calendar_execution.ActionAlreadyHandledError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/calendar/disconnect")
def calendar_disconnect():
    """Trennt die Google-Verbindung (Tokens werden gelöscht)."""
    return {"disconnected": calendar_client.disconnect()}
