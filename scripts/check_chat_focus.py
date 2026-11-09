"""Zwei echte Modellproben mit fiktiven Werkzeugdaten, ohne DB-/Kalenderzugriff."""

from datetime import datetime, time, timedelta
from pathlib import Path
import sys
from unittest.mock import patch


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.config import load_environment
    load_environment()
    from app.agent import assistant
    from app.tools.dates import BERLIN, today_berlin

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    start = today_berlin() + timedelta(days=14)
    end = start + timedelta(days=2)
    event_start = datetime.combine(start + timedelta(days=1), time(10), BERLIN)
    event_end = event_start + timedelta(hours=6)
    event = {
        "calendar_id": "demo", "event_id": "workshop", "title": "Teamworkshop",
        "start": event_start.isoformat(), "end": event_end.isoformat(), "all_day": False,
    }
    names = {"search_threads", "search_memories", "list_threads", "get_thread",
             "list_calendars", "list_events", "compute_date"}
    tools = [tool for tool in assistant.TOOLS if tool["name"] in names]
    original = assistant.execute_tool
    cases = [
        ("Terminkonflikt", f"Passt meine angedachte Kurzreise vom {start:%d.%m.%Y} bis {end:%d.%m.%Y}?",
         {"id": 1, "title": "Kurzreise", "status": "proposed", "tags": ["privat"],
          "event_start": start.isoformat(), "event_end": end.isoformat(), "time_precision": "exact"}),
        ("Offener Zeitraum", "Was steht bei meinem Werkstattprojekt als Nächstes an?",
         {"id": 1, "title": "Werkstattprojekt", "status": "proposed", "tags": ["privat"],
          "description": "Der gewünschte Monat für den Umbau ist noch offen.",
          "event_start": None, "event_end": None, "next_action": "Zeitraum klären"}),
    ]
    all_ok = True
    for label, question, target in cases:
        calls = []
        threads = [target, {"id": 2, "title": "Projektabgabe", "status": "active", "tags": ["arbeit"],
                            "deadline": (end + timedelta(days=1)).isoformat(), "next_action": "Abgabe vorbereiten"}]

        def execute(name, arguments, *args, **kwargs):
            calls.append(name)
            if name == "search_memories":
                return []
            if name == "search_threads":
                return [target]
            if name == "list_threads":
                return [t for t in threads if (not arguments.get("status") or t["status"] == arguments["status"])
                        and (not arguments.get("tag") or arguments["tag"] in t["tags"])]
            if name == "get_thread":
                return next((t for t in threads if t["id"] == arguments["thread_id"]), {"found": False})
            if name == "list_calendars":
                return [{"id": "demo", "summary": "Beispielkalender", "access_role": "reader"}]
            if name == "list_events":
                lower = datetime.fromisoformat(arguments["time_min"].replace("Z", "+00:00"))
                upper = datetime.fromisoformat(arguments["time_max"].replace("Z", "+00:00"))
                return [event] if lower < event_end and upper > event_start else []
            if name == "compute_date":
                return original(name, arguments)
            raise ValueError("Nur simulierte lesende Werkzeuge erlaubt.")

        try:
            with patch.object(assistant, "execute_tool", execute), \
                 patch.object(assistant, "web_search_limit", return_value=0), \
                 patch.object(assistant, "client", assistant.client.with_options(timeout=90, max_retries=0)):
                answer = assistant.run_tool_loop(assistant.build_instructions(),
                                                [{"role": "user", "content": question}], tools, max_rounds=6)
            words = len(answer.split())
            ok = words <= 100 and answer.count("?") <= 1
            ok = ok and not any(term in answer.lower() for term in ("thread", "proposed", "search_threads"))
            if label == "Terminkonflikt":
                ok = ok and {"list_threads", "list_events"}.issubset(calls) and "workshop" in answer.lower()
            print(f"{label}: {words} Wörter; Prüfung {'OK' if ok else 'auffällig'}; Werkzeuge: {', '.join(calls)}", flush=True)
            print(answer, flush=True)
            all_ok = all_ok and ok
        except Exception as exc:
            print(f"{label}: {type(exc).__name__}", flush=True)
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
