# Hugo

Proaktiver persönlicher Assistent: FastAPI-Backend, zentraler
LLM-Agent mit Werkzeugen (Erinnerungen, Vorhaben/Threads,
proaktive Vorschläge), PostgreSQL mit pgvector.

Details zu Mission, Architektur und Roadmap: [AGENTS.md](AGENTS.md).

## Entwicklung (Codespace / Lokal)

### Voraussetzungen

- Python 3.12+ mit virtueller Umgebung (`.venv`)
- Docker (für PostgreSQL via Compose)
- `OPENAI_API_KEY` als Umgebungsvariable

### Start

```bash
# Datenbank starten (Schema und Migrationen laufen automatisch)
docker compose up -d db

# Abhängigkeiten installieren
.venv/bin/pip install -r backend/requirements.txt

# Server starten
cd backend
OPENAI_API_KEY=... ../.venv/bin/python -m uvicorn app.main:app --port 8000
```

## Produktion (Docker Compose auf Proxmox)

Für den Betrieb auf einer Proxmox-VM mit Docker Compose:

```bash
# Umgebungsdatei vorbereiten
cp .env.prod.template .env.prod
# Editiere .env.prod: DB_PASSWORD, OPENAI_API_KEY, etc.

# Services starten (PostgreSQL, Web-Server, Background-Worker)
docker compose -f compose.prod.yaml --env-file .env.prod up -d

# Status prüfen
docker compose -f compose.prod.yaml ps

# Logs anschauen
docker compose -f compose.prod.yaml logs -f web
```

**Siehe [DEPLOYMENT.md](./DEPLOYMENT.md) für vollständige Dokumentation:**
- Erste Installation
- Täglicher Betrieb (Start/Stop/Restart)
- Backup & Restore
- Updates und Datenbankmigrationen
- Troubleshooting
- Externe Erreichbarkeit (Reverse-Proxy)

## Weboberfläche (MVP 0.1)

Nach dem Start unter <http://localhost:8000/ui> erreichbar
(leitet auf „Heute" weiter). Serverseitig gerendert mit Jinja2,
ohne Build-Schritt und ohne externe CDN-Abhängigkeiten; responsiv
für Desktop und Smartphone.

- **Chat** (`/ui/chat`): Nachrichten an Hugo senden, Verlauf
  lesen und fortsetzen, neue Unterhaltung beginnen. Links steht
  die Liste jüngster Unterhaltungen. Ladezustand („Hugo denkt
  nach …") und Fehler werden angezeigt; bei einem Fehler bleibt
  der Entwurf erhalten.
- **Heute** (`/ui/heute`): offene Vorschläge mit Priorität
  (P1–P5), Bezug zum Vorhaben, Datums- und Dringlichkeitshinweisen
  („in 3 Tagen", „seit gestern"). Vorschläge lassen sich
  bestätigen, zurückstellen oder verwerfen; zurückgestellte sind
  einklappbar. „Jetzt auswerten" startet manuell einen
  Evaluationslauf der Proaktivitäts-Engine.
- **Vorhaben** (`/ui/threads`): Threads gruppiert nach Status
  (Aktiv, Wartet, Idee, Erledigt/Archiviert einklappbar) mit
  nächster Aktion, Ereigniszeitraum, „handeln bis" (`act_by`)
  und Deadline. Detailansicht unter `/ui/threads/{id}` inklusive
  zugehöriger Vorschläge. Inhaltliche Änderungen erfolgen
  bewusst über den Chat, nicht über Formulare.

Die JSON-API bleibt unverändert verfügbar (`/docs` für Swagger UI;
`GET /` liefert weiterhin den Status als JSON). Neu hinzugekommen
ist lediglich der lesende Endpunkt `GET /conversations`
(jüngste Unterhaltungen mit Vorschau).

## Tests

```bash
.venv/bin/python -m pytest tests/
```

Die Web-Tests (`tests/test_web.py`) ersetzen Storage- und
Agentenfunktionen per Monkeypatch und brauchen weder Datenbank
noch OpenAI-Zugang. Integrations-Tests werden übersprungen,
wenn keine Datenbank erreichbar ist.

## Neue Komponenten (Produktion)

- **Dockerfile**: Multi-stage Build (schlankes Image, ~800 MB)
- **compose.prod.yaml**: Web-Server, Background-Worker, PostgreSQL
- **app/worker.py**: APScheduler für tägliche proaktive Auswertung
- **app/migrate.py**: Idempotente Migrations-Runner
- **.env.prod.template**: Template für Produktionssecrets
- **DEPLOYMENT.md**: Vollständige Betriebsdokumentation

## Einschränkungen (Stand MVP 0.1)

- Keine Authentifizierung: nur im vertrauenswürdigen lokalen
  Umfeld betreiben.
- Vorschläge erscheinen erst nach manueller oder geplanter
  Auswertung (täglich um 06:00 UTC im Produktivbetrieb).
- Ohne JavaScript bleibt alles nutzbar, es fehlen nur
  Ladeanzeige, Bestätigungsdialog und Enter-zum-Senden.
- Unterhaltungen haben keine Titel; die Liste zeigt die erste
  Nutzernachricht als Vorschau.
- Kein Kalender, kein Push, keine Benutzerverwaltung.
