"""Gemeinsame Chat-Logik für API-Endpunkt und Weboberfläche."""

from app.agent.assistant import ask_hugo
from app.agent.chat_context import prepare_context
from app.storage.database import (
    create_conversation,
    get_messages,
    save_message,
)


class ConversationNotFoundError(Exception):
    """Unterhaltung unbekannt oder noch ohne Nachrichten."""


def run_chat(message: str, conversation_id: int | None) -> dict:
    """Speichert die Nutzernachricht und erzeugt Hugos Antwort.

    Legt ohne conversation_id eine neue Unterhaltung an.
    """
    if conversation_id is None:
        conversation_id = create_conversation()
    elif not get_messages(conversation_id):
        raise ConversationNotFoundError(
            f"Unterhaltung {conversation_id} nicht gefunden."
        )

    message_id = save_message(conversation_id, "user", message)
    messages = prepare_context(conversation_id, message_id)
    answer = ask_hugo(messages, message_id)
    save_message(conversation_id, "assistant", answer)

    return {"conversation_id": conversation_id, "answer": answer}
