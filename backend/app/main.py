
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent.assistant import ask_hugo
from app.storage.memory_search import list_memories
from app.storage.database import (
    create_conversation,
    save_message,
    get_messages,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Hugo", version="0.3.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: int | None = None


@app.get("/")
def root():
    return {
        "name": "Hugo",
        "version": "0.3.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest):
    conversation_id = request.conversation_id

    # Neue Unterhaltung anlegen
    if conversation_id is None:
        conversation_id = create_conversation()

    # Bestehende Unterhaltung prüfen
    else:
        if not get_messages(conversation_id):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found or empty",
            )

    # Nutzernachricht speichern
    message_id = save_message(
        conversation_id,
        "user",
        request.message,
    )

    # Gesprächshistorie laden
    messages = get_messages(conversation_id)

    # KI-Antwort erzeugen
    answer = ask_hugo(messages, message_id)

    # KI-Antwort speichern
    save_message(
        conversation_id,
        "assistant",
        answer,
    )

    return {
        "conversation_id": conversation_id,
        "answer": answer,
    }

@app.get("/memories")
def get_memories(limit: int = 100):
    limit = max(1, min(limit, 500))
    return {"memories": list_memories(limit)}

@app.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: int):
    messages = get_messages(conversation_id)

    if not messages:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or empty",
        )

    return messages
