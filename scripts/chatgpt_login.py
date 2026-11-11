"""Manual OAuth setup and a small, explicit inference check; no work at import."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import parse_qs, urlparse


def login(auth, storage, port):
    host_id, previous = storage.read_registration()
    result = {}
    pending = None

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Authorization codes and state must never enter access logs.

        def do_GET(self):
            parsed = urlparse(self.path)
            values = parse_qs(parsed.query)
            valid_state = len(values.get("state", [])) == 1 and secrets.compare_digest(
                values["state"][0], pending["state"],
            )
            if parsed.path != "/auth/callback" or not valid_state or any(len(v) != 1 for v in values.values()):
                self.send_error(400, "Invalid callback")
                return
            try:
                registration = auth.complete_authorization(pending, {k: v[0] for k, v in values.items()})
                with storage.locked_registration() as (_, current):
                    if current != previous:
                        raise auth.ChatGPTAuthError("Die Verbindung wurde inzwischen geändert. Anmeldung erneut starten.")
                    current.clear()
                    current.update(registration)
                result["ok"] = True
                message = "Hugo ist verbunden. Geeignete KI-Anfragen nutzen dein ChatGPT-Abo. Nutzung in den ChatGPT-Einstellungen verwalten. Du kannst dieses Fenster schliessen."
            except auth.ChatGPTAuthError as exc:
                result["error"] = str(exc)
                message = str(exc)
            self.send_response(200 if result.get("ok") else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(message.encode("utf-8"))

    with HTTPServer(("127.0.0.1", port), Callback) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
        pending, url = auth.authorization(host_id, previous, redirect)
        print("Continue with ChatGPT – diesen Link im lokalen Browser öffnen:", flush=True)
        print(url, flush=True)
        print("Warte höchstens 10 Minuten auf die Anmeldung …", flush=True)
        while not result and time.monotonic() - pending["started_at"] < 600:
            server.handle_request()
    if not result.get("ok"):
        raise auth.ChatGPTAuthError(result.get("error", "Anmeldung abgelaufen."))
    print("Verbunden. Geeignete Modellaufrufe nutzen dein ChatGPT-Abo. Mit 'models' verfügbare Modelle anzeigen.")


def main():
    parser = argparse.ArgumentParser(description="Hugo mit dem ChatGPT-Abo verbinden")
    parser.add_argument("command", choices=["login", "status", "models", "check", "resume", "logout"])
    parser.add_argument("--port", type=int, default=0, help="Lokaler OAuth-Port; 0 wählt einen freien Port")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.config import load_environment
    load_environment(args.env_file)
    from app.agent import chatgpt_auth as auth
    from app.storage import model_oauth as storage

    try:
        if args.command == "login":
            from app.migrate import run_migrations
            if run_migrations()["status"] != "ok":
                raise RuntimeError("Datenbankmigration fehlgeschlagen; Anmeldung nicht gestartet.")
            login(auth, storage, args.port)
        elif args.command == "status":
            from app.agent.model_client import usage_status
            _, registration = storage.read_registration()
            print("Verbunden:" if registration.get("refresh_token") else "Nicht verbunden:", registration.get("email", ""))
            print("Modellzugang:", usage_status())
        elif args.command == "models":
            for model in auth.model_catalog():
                print(model["slug"], "—", model.get("display_name", model["slug"]))
        elif args.command == "resume":
            from app.agent.model_usage import reset_quota_pause
            reset_quota_pause()
            print("Kontingentpause aufgehoben. Der nächste Aufruf prüft die Verfügbarkeit erneut.")
        elif args.command == "logout":
            print("Abgemeldet." if auth.sign_out() else
                  "Lokal abgemeldet. Widerruf nicht bestätigt; Hugo zusätzlich in ChatGPT-Einstellungen trennen.")
        else:
            from app.agent.model_client import ModelClient
            from app.settings import get_value
            response = ModelClient(provider_override="chatgpt", allow_api_fallback=False, timeout=60).responses.create(
                model=get_value("HUGO_MODEL", ""),
                input=[{"role": "user", "content": "Antworte ausschließlich mit OK."}],
            )
            print("OAuth-Modellaufruf abgeschlossen:", response.output_text)
            usage = getattr(response, "usage", None)
            print("Tokens:", getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
        return 0
    except (auth.ChatGPTAuthError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
