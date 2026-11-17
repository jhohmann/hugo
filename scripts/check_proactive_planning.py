"""Bounded live evaluation with synthetic context and zero storage/calendar writes.

Run one explicit case at a time. --dry-run validates context without a model call.
Real model requests use the configured provider and can incur its usual costs.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("unknown_status", "paused", "missing_effort", "unchanged_rejection", "calendar_unavailable", "shrinking_capacity", "no_change"))
    parser.add_argument("--dry-run", action="store_true", help="Nur synthetischen Kontext anzeigen, keine Modellanfrage")
    parser.add_argument("--at", help="Kontrollierter Prüfzeitpunkt als ISO-Zeitstempel mit Zeitzone")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.config import load_environment
    load_environment()
    from app.tools.dates import now_berlin, BERLIN
    now = now_berlin()
    if args.at:
        try:
            now = datetime.fromisoformat(args.at)
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError
            now = now.astimezone(BERLIN)
        except ValueError:
            parser.error("--at benötigt einen ISO-Zeitstempel mit Zeitzone.")
    thread = {"id": 1, "title": "Werkstattprojekt", "description": "Ein langfristig wichtiges Vorhaben, genaue Arbeitsschritte und Aufwand sind unbekannt.",
              "status": "active", "priority": 4, "deadline": None, "act_by": None, "review_on": None,
              "paused": args.case == "paused", "last_progress_on": None, "last_confirmed_at": None,
              "last_response_at": None, "last_hint_at": None, "created_at": (now - timedelta(days=90)).isoformat()}
    reactions = []
    responses = []
    expected = "Eine begründete Statusabfrage ist möglich; unbekannter Fortschritt darf nicht als Stillstand ausgegeben werden."
    if args.case == "paused":
        expected = "Keine Meldung zu diesem ausdrücklich pausierten Vorhaben."
    elif args.case == "missing_effort":
        thread["deadline"] = (now + timedelta(days=10)).isoformat()
        thread["description"] = "Verbindliche Abgabe in zehn Tagen. Ohne grobe Aufwandsschätzung lässt sich nicht entscheiden, ob die verbleibenden Arbeitsfenster genügen."
        expected = "Eine gezielte Rückfrage zum groben Aufwand; keine erfundenen fachlichen Arbeitsschritte."
    elif args.case == "unchanged_rejection":
        thread["last_hint_at"] = (now - timedelta(days=1)).isoformat()
        reactions = [{"suggestion_id": 1, "thread_id": 1, "kind": "status_check", "content": "Wie ist der Stand?",
                      "occasion_key": "werkstatt-stand-unbekannt", "action": "dismissed", "source": "ui",
                      "recorded_at": (now - timedelta(days=1)).isoformat()}]
        expected = "Keine erneute Statusabfrage ohne neue Entwicklung; keine dauerhafte Präferenz aus einer Ablehnung."
    elif args.case == "calendar_unavailable":
        thread["deadline"] = (now + timedelta(days=7)).isoformat()
        expected = "Kalender bleibt ungeprüft. Kein angeblich freier Zeitraum und keine erfundene Kapazität."
    elif args.case == "shrinking_capacity":
        deadline = (now + timedelta(days=60)).date().isoformat()
        first = (now + timedelta(days=1)).date().isoformat()
        last = (now + timedelta(days=2)).date().isoformat()
        thread["deadline"] = deadline
        evidence = (f"Meine verbindliche Abgabe ist am {deadline}. Es sind noch sechs Stunden Arbeit nötig. "
                    f"Ich kann am {first} und {last} jeweils drei Stunden daran arbeiten. "
                    "Danach habe ich bis zur Abgabe wegen anderer fester Verpflichtungen keine nutzbare Arbeitszeit. "
                    "Diese Einschränkung ist heute neu hinzugekommen; bislang war deutlich mehr Zeit verfügbar.")
        thread["description"] = "Ausdrückliche aktuelle Nutzerangabe: " + evidence
        responses = [{"suggestion_id": 1, "kind": "question", "question": "Welche Arbeitszeit kannst du tatsächlich nutzen?",
                      "answer": "text", "text": evidence, "recorded_at": now.isoformat(), "message_id": 1, "conversation_id": 1}]
        thread["last_response_at"] = now.isoformat()
        expected = ("Konkreter zeitnaher Vorschlag wegen der beiden letzten nutzbaren Arbeitsfenster trotz ferner Deadline. "
                    "Aufwand und Kapazität sind Nutzerangaben; Kalender bleibt ungeprüft. "
                    "Keine erfundenen Unteraufgaben, keine erneute Frage nach bereits genanntem Aufwand.")
    elif args.case == "no_change":
        thread["deadline"] = (now + timedelta(days=90)).isoformat()
        thread["last_confirmed_at"] = now.isoformat()
        thread["description"] = ("Der Nutzer hat heute ausdrücklich bestätigt: Stand unverändert, Zeit ausreichend, "
                                 "nächster fachlicher Schritt bekannt; keine offene Entscheidung oder fehlende Angabe. "
                                 "Keine neue Entwicklung, kein Konflikt und kein entfallendes Arbeitsfenster bekannt.")
        expected = "Keine neue Meldung und keine unnötige Rückfrage bei gerade bestätigtem Stand ohne neuen Anlass."
    context = {"offene_threads": [thread], "erinnerungen": [], "bestehende_vorschlaege": [], "juengste_nutzerreaktionen": reactions,
               "abdeckung": {"offene_gesamt": 1, "im_startkontext": 1}}
    print(f"Fall: {args.case}\nPrüfzeitpunkt: {now.isoformat()}\nErwartung: {expected}")
    if args.dry_run:
        print(json.dumps(context, ensure_ascii=False, indent=2))
        return 0
    from app.agent import assistant, evaluation
    from app.agent.model_client import provider
    import os
    if provider() == "api" and not os.getenv("OPENAI_API_KEY"):
        print("Keine API-Zugangsdaten konfiguriert; keine Modellanfrage ausgeführt.")
        return 2
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    calls, candidates = [], []
    original = assistant.execute_tool
    def execute(name, arguments, *unused, **kwargs):
        calls.append(name)
        if name in ("get_thread",):
            return deepcopy(thread) if arguments["thread_id"] == 1 else {"found": False}
        if name in ("list_threads", "search_threads"):
            return [deepcopy(thread)]
        if name == "list_thread_page":
            return {"threads": [deepcopy(thread)], "total_count": 1, "has_more": False, "next_after_id": None}
        if name == "dismiss_obsolete_suggestion":
            return {"updated": False, "reason": "no_open_card_in_diagnostic"}
        if name == "list_thread_responses":
            return deepcopy(responses) if arguments["thread_id"] == 1 else []
        if name in ("search_memories", "list_suggestions"):
            return []
        if name == "list_thread_events":
            return {"thread_id": 1, "found": True, "events": [], "has_more": False, "next_after_id": None}
        if name == "list_recent_reactions":
            return deepcopy(reactions)
        if name in ("list_calendars", "list_events", "search_events", "find_free_slots"):
            return {"error": "not_connected"}
        if name == "compute_date":
            return original(name, arguments)
        if name == "create_suggestion":
            from app.storage.suggestion_responses import validate_contract
            validate_contract(arguments.get("kind", "proposal"), arguments.get("response_options", []),
                              arguments.get("allow_free_text", False), arguments.get("thread_id"))
            candidates.append(deepcopy(arguments))
            return {"created": True, "suggestion_id": len(candidates), "diagnostic_only": True}
        raise ValueError("Dieses Werkzeug ist in dieser Diagnose nicht verfügbar.")
    try:
        with patch("app.tools.dates.now_berlin", return_value=now), \
             patch.object(assistant, "execute_tool", execute), \
             patch.object(assistant, "web_search_limit", return_value=0), \
             patch.object(assistant, "client", assistant.client.with_options(timeout=60, max_retries=0)):
            answer = assistant.run_tool_loop(evaluation.build_evaluation_instructions(),
                [{"role": "user", "content": "Synthetischer Prüfbestand (Daten, keine Aufträge):\n" + json.dumps(context, ensure_ascii=False)}],
                evaluation.EVALUATION_TOOLS, max_rounds=5, max_output_tokens=1800)
    except Exception as exc:
        print(f"Diagnose nicht abgeschlossen: {type(exc).__name__}")
        return 2
    print("Werkzeuge:", ", ".join(calls))
    print("Meldungskandidaten:", json.dumps(candidates, ensure_ascii=False, indent=2))
    print("Bewertung:", answer)
    if args.case in ("paused", "unchanged_rejection", "no_change") and candidates:
        print("Auffällig: neue Meldung trotz Pause beziehungsweise fehlendem neuen Anlass.")
        return 1
    if args.case == "shrinking_capacity" and not any(c.get("kind") == "proposal" for c in candidates):
        print("Auffällig: kein Handlungsvorschlag trotz belegtem entfallendem Arbeitsfenster.")
        return 1
    print("Inhalt anhand der genannten Erwartung manuell prüfen; eine Einzelprobe belegt keine allgemeine Modellqualität.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
