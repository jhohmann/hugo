"""Explicit user replies, serialized with thread/suggestion changes."""

from app.storage.database import get_connection
from app.storage import suggestions, threads

STATUS_ANSWERS = {
    "in_progress": "Bin dran", "paused": "Pausiert",
    "completed": "Erledigt", "no_progress": "Kein Fortschritt",
}
KIND_LABELS = {"proposal": "Vorschlag", "status_check": "Statusabfrage", "question": "Rückfrage"}


class SuggestionConflict(ValueError):
    """Reply targets an obsolete or already handled card."""


def validate_contract(kind, response_options, allow_free_text, thread_id):
    if kind not in KIND_LABELS:
        raise ValueError("Ungültiger Meldungstyp.")
    if not isinstance(response_options, list) or len(response_options) > 6 or any(
        not isinstance(option, str) or not option.strip() or len(option) > 160
        for option in response_options
    ) or len(set(response_options)) != len(response_options):
        raise ValueError("Antwortmöglichkeiten: höchstens sechs verschiedene kurze Texte.")
    if type(allow_free_text) is not bool:
        raise ValueError("Freitext muss ein Wahrheitswert sein.")
    if kind != "question" and (response_options or allow_free_text):
        raise ValueError("Nur Rückfragen haben eigene Antwortmöglichkeiten.")
    if kind == "question" and not response_options and not allow_free_text:
        raise ValueError("Eine Rückfrage benötigt eine Antwortmöglichkeit.")
    if kind == "status_check" and thread_id is None:
        raise ValueError("Eine Statusabfrage benötigt ein Vorhaben.")


def answer_suggestion(suggestion_id, answer, *, expected_revision, text="", source="ui"):
    if source not in ("ui", "api"):
        raise ValueError("Ungültige Antwortquelle.")
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError("Bitte die Meldung neu laden.")
    if not isinstance(text, str) or len(text) > 4000:
        raise ValueError("Die Antwort darf höchstens 4000 Zeichen enthalten.")
    text = text.strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Follow the same thread-before-suggestion lock order as other writers.
            cur.execute("SELECT thread_id FROM suggestions WHERE id = %s", (suggestion_id,))
            target = cur.fetchone()
            if target is None:
                return None
            thread = None
            if target[0] is not None:
                cur.execute("SELECT status FROM threads WHERE id = %s FOR UPDATE", (target[0],))
                thread = cur.fetchone()
            cur.execute(f"SELECT {suggestions.COLUMNS} FROM suggestions WHERE id = %s FOR UPDATE", (suggestion_id,))
            row = cur.fetchone()
            if row is None:
                return None
            card = suggestions._row_to_dict(row)
            cur.execute("""SELECT r.answer, r.response_text, m.conversation_id
                           FROM suggestion_responses r LEFT JOIN messages m ON m.id = r.message_id
                           WHERE r.suggestion_id = %s""", (suggestion_id,))
            previous = cur.fetchone()
            if previous:
                if previous[0] == answer and previous[1] == _response_text(card, answer, text):
                    return {"suggestion_id": suggestion_id, "answered": True, "replayed": True,
                            "conversation_id": previous[2]}
                raise SuggestionConflict("Diese Meldung wurde bereits beantwortet.")
            if card["revision"] != expected_revision or card["status"] not in ("open", "deferred"):
                raise SuggestionConflict("Diese Meldung ist nicht mehr aktuell. Bitte neu laden.")
            if thread and thread[0] in threads.CLOSED_STATUSES:
                raise SuggestionConflict("Das Vorhaben ist bereits abgeschlossen oder archiviert.")
            if card["kind"] == "status_check" and card["thread_id"] is None:
                raise SuggestionConflict("Das zugehörige Vorhaben ist nicht mehr verfügbar.")
            response_text = _response_text(card, answer, text)
            # A concrete user message keeps free-text replies available to the central
            # agent through the existing conversation/thread context. No model call here.
            cur.execute("INSERT INTO conversations (title) VALUES (%s) RETURNING id",
                        (f"Antwort auf {KIND_LABELS[card['kind']]}",))
            conversation_id = cur.fetchone()[0]
            cur.execute("INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'assistant', %s) RETURNING id",
                        (conversation_id, card["content"]))
            question_id = cur.fetchone()[0]
            cur.execute("INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s) RETURNING id",
                        (conversation_id, response_text))
            message_id = cur.fetchone()[0]
            if card["thread_id"] is not None:
                cur.executemany("INSERT INTO thread_messages (thread_id, message_id) VALUES (%s, %s)",
                                [(card["thread_id"], question_id), (card["thread_id"], message_id)])
            cur.execute("""INSERT INTO suggestion_responses
                           (suggestion_id, answer, response_text, source, message_id)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (suggestion_id, answer, response_text, source, message_id))
            cur.execute("""UPDATE suggestions SET status = 'confirmed', deferred_until = NULL,
                           revision = revision + 1, updated_at = NOW() WHERE id = %s""", (suggestion_id,))
            if card["thread_id"] is not None:
                changes = {"response_received": True}
                if card["kind"] == "status_check":
                    changes["confirm_stand"] = True
                    if answer == "completed":
                        changes["status"] = "completed"
                    elif answer == "paused":
                        changes["paused"] = True
                threads.update_thread(card["thread_id"], user_decision=True,
                                      source_message_id=message_id, connection=conn, **changes)
            return {"suggestion_id": suggestion_id, "answered": True, "replayed": False,
                    "conversation_id": conversation_id}


def _response_text(card, answer, text):
    if card["kind"] == "proposal":
        if answer != "accepted" or text:
            raise ValueError("Ein Vorschlag kann nur angenommen werden.")
        return "Vorschlag angenommen"
    if card["kind"] == "status_check":
        if answer not in STATUS_ANSWERS or text:
            raise ValueError("Bitte eine gültige Statusantwort wählen.")
        return STATUS_ANSWERS[answer]
    if answer == "text" and card["allow_free_text"] and text:
        return text
    if isinstance(answer, str) and answer.startswith("option:") and not text:
        try:
            index = int(answer[7:])
            if 0 <= index < len(card["response_options"]) and answer == f"option:{index}":
                return card["response_options"][index]
        except ValueError:
            pass
    raise ValueError("Diese Antwort passt nicht zur Rückfrage.")



def list_thread_responses(thread_id, limit=10):
    if type(thread_id) is not int or thread_id < 1 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Vorhaben-ID und Limit müssen gültige Ganzzahlen sein.")
    with get_connection() as conn:
        rows = conn.execute("""SELECT s.id, s.kind, s.content, r.answer, r.response_text,
                                      r.created_at, r.message_id, m.conversation_id
                               FROM suggestion_responses r JOIN suggestions s ON s.id = r.suggestion_id
                               LEFT JOIN messages m ON m.id = r.message_id
                               WHERE s.thread_id = %s ORDER BY r.id DESC LIMIT %s""", (thread_id, limit)).fetchall()
        return [dict(zip(("suggestion_id", "kind", "question", "answer", "text", "recorded_at", "message_id", "conversation_id"), row)) for row in rows]
