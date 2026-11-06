"""Zeitgesteuerte Bestandsbewertung (Proaktivitäts-Engine).

Derselbe zentrale Agent wie im Chat bewertet hier den
Bestand ohne eingehende Nutzernachricht. Python übernimmt
Datenzugriff, Lauf-Verwaltung und Ausführung; das Modell
entscheidet, was Aufmerksamkeit verdient.
"""

import json
import logging

from app.agent.assistant import TOOLS, run_tool_loop
from app.storage.memory_search import list_memories
from app.storage.suggestions import (
    count_suggestions_for_run,
    create_run,
    finish_run,
    list_suggestions,
)
from app.storage.threads import list_threads
from app.tools.dates import current_time_context

logger = logging.getLogger(__name__)

EVALUATION_PROMPT = """
Du bist Hugo, ein persönlicher, vorausschauender KI-Assistent.

Du führst jetzt eine zeitgesteuerte Bestandsbewertung durch.
Der Nutzer hat KEINE Nachricht gesendet. Bewerte die offenen
Vorhaben (Threads) und Erinnerungen anhand des aktuellen
Zeitkontexts und entscheide selbstständig, ob etwas
Aufmerksamkeit verdient.

BEWERTE INSBESONDERE
- Bereiche (tags): arbeit und privat liefern Kontext. Berücksichtige
  beide Bereiche und unzugeordnete Vorhaben; keiner hat pauschal Vorrang.
- bevorstehende oder überfällige Vorbereitungszeitpunkte
  (act_by)
- harte Deadlines
- Ereignisse und ungefähre Zeiträume (event_start/event_end,
  time_precision)
- Vorbereitungsfenster: Wenn ein Thread preparation_weeks
  hat, prüfe ob event_start oder act_by innerhalb dieses
  Fensters liegt. Beispiel: preparation_weeks=12 und
  event_start in 10 Wochen → Zeit zu starten.
- Blocker: Threads mit blocked_reason warten auf etwas.
  Prüfe ob der Grund noch aktuell ist und ob nachgefasst
  werden sollte.
- offene Entscheidungen und fehlende Informationen, die
  rechtzeitiges Handeln verhindern
- mögliche Konflikte und Abhängigkeiten zwischen Vorhaben
  (erkennbar aus Beschreibung und Kontext)
- sofern ein Kalender verbunden ist: Terminkonflikte mit
  Vorhaben (list_events, find_free_slots; bei
  "not_connected" den Kalender einfach ignorieren)

VORSCHLÄGE
- Erzeuge mit create_suggestion nur konkrete, nützliche
  Vorschläge mit Begründung, Priorität und — wenn sinnvoll —
  einem empfohlenen Handlungszeitpunkt.
- Schlecht: "Japanreise am 15. März". Gut: "Die Japanreise
  beginnt in etwa vier Monaten; Flugbuchung und Prüfung der
  Einreisevoraussetzungen sollten jetzt angegangen werden."
- Bei Vorbereitungsfenstern: "Die Japanreise beginnt in
  10 Wochen, preparation_weeks=12. Es ist Zeit zu starten.
  Das Visum ist noch nicht beantragt — das ist der erste
  Schritt."
- Bei Blockern: "Thread X wartet seit 2 Wochen auf Y.
  Nachfassen?"
- Erzeuge keine Vorschläge, wenn nichts relevant ist.
- Wiederhole keine bestehenden offenen oder zurückgestellten
  Vorschläge (siehe Eingabe).
- Vorschläge bleiben intern; keine externen Aktionen.
- Nutze search_threads, list_threads, get_thread oder
  search_memories bei Bedarf für weiteren Kontext.

Schließe mit einer kurzen Zusammenfassung deiner Bewertung
ab (auf Deutsch, sachlich).
"""

# Während der Bewertung darf der Agent nur lesen und
# Vorschläge erzeugen — keine Änderungen an Threads oder
# Erinnerungen. Kalenderzugriff ist hier ausschließlich
# lesend (Terminvorschläge bleiben dem Chat vorbehalten).
_READ_TOOL_NAMES = {
    "search_memories",
    "search_threads",
    "list_threads",
    "get_thread",
    "list_calendars",
    "list_events",
    "find_free_slots",
}

_SUGGESTION_TOOL = {
    "type": "function",
    "name": "create_suggestion",
    "description": (
        "Erstellt einen proaktiven Vorschlag zu einem Vorhaben. "
        "Nur für konkrete, aktuell relevante Handlungsanlässe. "
        "Keine Wiederholung bestehender offener oder "
        "zurückgestellter Vorschläge."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "thread_id": {
                "type": ["integer", "null"],
                "description": (
                    "Zugehöriger Thread; null bei "
                    "themenübergreifenden Vorschlägen."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Konkreter, hilfreicher Vorschlagstext."
                ),
            },
            "reason": {
                "type": ["string", "null"],
                "description": "Begründung: warum jetzt relevant.",
            },
            "priority": {
                "type": ["integer", "null"],
                "description": "1 = niedrig bis 5 = hoch.",
                "minimum": 1,
                "maximum": 5,
            },
            "suggested_date": {
                "type": ["string", "null"],
                "description": (
                    "Empfohlener Handlungszeitpunkt (ISO-Datum)."
                ),
            },
        },
        "required": [
            "thread_id", "content", "reason",
            "priority", "suggested_date",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}

EVALUATION_TOOLS = [
    tool for tool in TOOLS if tool["name"] in _READ_TOOL_NAMES
] + [_SUGGESTION_TOOL]


def build_evaluation_instructions() -> str:
    return (
        EVALUATION_PROMPT
        + "\n\nZEITKONTEXT\n"
        + current_time_context()
    )


def run_evaluation(trigger: str = "manual") -> dict:
    """Ein Evaluationslauf über den aktuellen Bestand.

    Nachvollziehbar über einen Eintrag in evaluation_runs;
    Fehler markieren den Lauf als 'failed' und werden
    weitergemeldet.
    """
    run_id = create_run(trigger)
    try:
        threads = list_threads(open_only=True, limit=50)
        memories = list_memories(limit=30)
        existing = [
            s
            for s in list_suggestions(limit=100)
            if s["status"] in ("open", "deferred")
        ]

        payload = {
            "offene_threads": threads,
            "erinnerungen": memories,
            "bestehende_vorschlaege": existing,
        }
        input_messages = [
            {
                "role": "user",
                "content": (
                    "Aktueller Bestand zur Bewertung (JSON):\n"
                    + json.dumps(
                        payload, ensure_ascii=False, default=str
                    )
                ),
            }
        ]

        summary = run_tool_loop(
            build_evaluation_instructions(),
            input_messages,
            EVALUATION_TOOLS,
            run_id=run_id,
            max_output_tokens=3000,
        )

        created = count_suggestions_for_run(run_id)
        finish_run(
            run_id,
            status="completed",
            threads_considered=len(threads),
            suggestions_created=created,
        )
        return {
            "run_id": run_id,
            "status": "completed",
            "threads_considered": len(threads),
            "suggestions_created": created,
            "summary": summary,
        }

    except Exception as exc:
        logger.exception("Evaluation run %s failed", run_id)
        finish_run(run_id, status="failed", error=str(exc))
        raise
