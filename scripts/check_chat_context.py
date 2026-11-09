"""Small live summary/recall check using synthetic data, without database writes."""

import json
import logging
import os
from pathlib import Path
import sys
from unittest.mock import patch


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.config import load_environment
    load_environment()
    from app.agent import assistant, chat_context

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Synthetic, explicit dates make the check independent of today's date.
    facts = [
        "Projekt Atlas: Ziel 12. Dezember 2026, hohe Priorität. Baustein von Nord fehlt; Kontakt Lara.",
        "Vorschlag: Arbeitsbeginn 5. Dezember. Es wurde kein Kalendertermin erstellt.",
        "Korrektur: Ziel ist 18. Dezember 2026, keine harte Frist. Atlas bleibt eine unverbindliche Option. Morgen will ich nachfragen.",
        "Verstanden, die Option ist noch nicht beschlossen.",
        "Nord entfällt. Wir warten auf den Baustein von Süd, Kontakt Mira. Priorität bleibt hoch.",
        "Die Rückmeldung von Süd steht also noch aus.",
    ]
    filler = " Wir haben die Formulierungen besprochen; daraus ergibt sich keine weitere Entscheidung."
    records = [{"id": i + 1, "role": "user" if i % 2 == 0 else "assistant",
                "content": (facts[i] if i < len(facts) else "Keine neuen Sachangaben.") + filler * 5,
                "created_at": "2026-11-09T10:00:00+01:00"} for i in range(18)]
    records.append({"id": 19, "role": "user", "created_at": "2026-11-09T12:00:00+01:00",
                    "content": "Korrektur: Atlas zielt jetzt auf den 21. Dezember 2026. "
                    "Nur aus unserem Gespräch, ohne Recherche: Gib ausschließlich ein JSON-Objekt "
                    "mit target_date (ISO), tentative (bool), waiting_for (Firmenname), contact, "
                    "followup_date (ISO, ursprüngliches morgen), calendar_created (bool) zurück."})
    cached = {}

    def load(*_):
        summary = cached.get("summary")
        return summary, [m for m in records if m["id"] > (summary or {}).get("through_message_id", 0)]

    def save(cid, through, content, expected):
        cached["summary"] = {"through_message_id": through, "content": content}
        return True

    loggers = [logging.getLogger(module.__name__) for module in (assistant, chat_context)]
    handler = logging.StreamHandler(sys.stdout)
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    try:
        with patch.dict(os.environ, {"HUGO_CHAT_HISTORY_TOKENS": "2000", "HUGO_WEB_SEARCH_ENABLED": "false"}), \
                patch.object(chat_context, "load_context", load), \
                patch.object(chat_context, "save_summary", save):
            prepared = chat_context.prepare_context(1, 19)
            assert cached.get("summary"), "No compaction occurred"
            assert chat_context.estimate_tokens(prepared) < 2000
            # A second preparation must be served without another model call.
            with patch.object(chat_context, "summarize", side_effect=AssertionError("Unexpected API call")):
                assert chat_context.prepare_context(1, 19) == prepared
            assistant.client = assistant.client.with_options(timeout=90, max_retries=0)
            answer = assistant.run_tool_loop(assistant.build_instructions(), prepared, [], max_rounds=1)
            result = json.loads(answer)
            assert result == {"target_date": "2026-12-21", "tentative": True,
                              "waiting_for": "Süd", "contact": "Mira",
                              "followup_date": "2026-11-10", "calendar_created": False}, result
            print(json.dumps({"status": "passed", "estimated_history_tokens_before":
                              chat_context.estimate_tokens(chat_context.as_input(None, records)),
                              "estimated_history_tokens_after": chat_context.estimate_tokens(prepared),
                              "recall": result}, ensure_ascii=False))
    except Exception as exc:
        print(f"Live-Test fehlgeschlagen: {type(exc).__name__}")
        return 1
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
