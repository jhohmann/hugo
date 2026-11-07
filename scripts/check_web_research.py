"""Begrenzter Live-Test der Webrecherche mit öffentlicher Frage, ohne DB-Zugriff."""

import argparse
import logging
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="Wann findet die nächste Red Bull Romaniacs statt? Prüfe den offiziellen Renntermin und nenne die Quelle.")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.config import load_environment
    load_environment()
    from app.agent import assistant

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Nur die eigene öffentliche Testfrage; keine bisherigen Chats und keine
    # lokalen Funktionswerkzeuge. Der Tool-Loop prüft diese Werkzeugfreigabe.
    assistant.client = assistant.client.with_options(timeout=90, max_retries=0)
    logger = logging.getLogger(assistant.__name__)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        answer = assistant.run_tool_loop(
            assistant.build_instructions(),
            [{"role": "user", "content": args.question}],
            [], max_rounds=3,
        )
        print(answer)
    except Exception as exc:
        # Keine HTTP-Header, Schlüssel oder vollständigen Providerfehler ausgeben.
        print(f"Live-Test fehlgeschlagen: {type(exc).__name__}")
        return 1
    finally:
        logger.removeHandler(handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
