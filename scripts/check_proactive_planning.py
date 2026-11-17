"""Bounded live evaluation with synthetic context and zero storage/calendar writes.

Run one explicit case at a time. --dry-run validates context without a model call.
Real model requests use the configured provider and can incur its usual costs.
"""

import argparse
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("unknown_status", "paused", "missing_effort", "unchanged_rejection", "calendar_unavailable"))
    parser.add_argument("--dry-run", action="store_true", help="Nur synthetischen Kontext anzeigen, keine Modellanfrage")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.config import load_environment
    load_environment()
    from app.tools.dates import now_berlin
    now = now_berlin()
    thread = {"id": 1, "title": "Werkstattprojekt", "description": "Ein langfristig wichtiges Vorhaben, genaue Arbeitsschritte und Aufwand sind unbekannt.",
              "status": "active", "priority": 4, "deadline": None, "act_by": None, "review_on": None,
              "paused": args.case == "paused", "last_progress_on": None, "last_confirmed_at": None,
              "last_response_at": None, "last_hint_at": None, "created_at": (now - timedelta(days=90)).isoformat()}
    reactions = []
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
    context = {"offene_threads": [thread], "erinnerungen": [], "bestehende_vorschlaege": [], "juengste_nutzerreaktionen": reactions,
               "abdeckung": {"offene_gesamt": 1, "im_startkontext": 1}}
    print(f"Fall: {args.case}\nErwartung: {expected}")
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
        if name in ("search_memories", "list_thread_responses", "list_suggestions"):
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
        with patch.object(assistant, "execute_tool", execute), \
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
    if args.case in ("paused", "unchanged_rejection") and candidates:
        print("Auffällig: neue Meldung trotz Pause beziehungsweise unverändert abgelehntem Anlass.")
        return 1
    print("Inhalt anhand der genannten Erwartung manuell prüfen; eine Einzelprobe belegt keine allgemeine Modellqualität.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
