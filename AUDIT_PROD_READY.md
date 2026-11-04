# Hugo Produktions-Vorbereitung: Audit-Bericht

**Datum:** 4. November 2026  
**Status:** Bestehende Codespace-Entwicklung ist funktionsfähig und stabil

## Bestehende Komponenten

### ✅ Backend-Architektur
- **FastAPI** Server (app/main.py) mit vollständiger API
- **Zentrale Agent-Loop** mit Tool-Calling (OpenAI gpt-5-mini)
- **Proaktivitäts-Engine** (run_evaluation, Suggestions-Persistierung)
- **Web-UI** (Jinja2, serverseitig gerendert)
- **PostgreSQL 17** mit pgvector via Docker Compose

### ✅ Datenbankschema (5 Migrationen + Basis-Schema)
```
001: schema.sql        → conversations, messages, memories, threads, etc.
002: embeddings.sql    → vectors für memories (384-dimensional HNSW)
003: thread_embeddings → vectors für threads
004: temporal.sql      → event_start, event_end, time_precision, act_by, time_text
005: proactivity.sql   → evaluation_runs, suggestions, suggestions_run_mapping
006: calendar.sql      → calendar_actions, calendar_sync_log (neu)
```

### ✅ Konfiguration (aktuell Dev)
- `DATABASE_URL` mit Default `postgres://...@localhost:5432/hugo`
- `OPENAI_API_KEY` als Umgebungsvariable
- Compose.yaml mit `127.0.0.1:5432` lokal gebunden

### ✅ Tests
- 90+ pytest-Tests (thread storage, tools, web UI)
- Keine DB/OpenAI-Abhängigkeiten für Web-Tests

---

## Fehlende Komponenten für Produktion

### 🔴 Docker-Infrastruktur
- **Kein Dockerfile** für die Hugo-App
- **Kein Produktions-Compose** (compose.prod.yaml)
- Keine Separation: Web-Server vs. Background-Worker
- Keine Secrets-Management (env-file Handling)
- Keine Health-Checks für die App
- Keine automatischen Restarts

### 🔴 Datenbank-Migrations-Handling
- Migrationen laufen nur beim Container-Start (`docker-entrypoint-initdb.d/`)
- Kein idempotentes Migrations-System für Updates (Replicas, Sicherung)
- Keine Versionskontrolle der Migrations-Reihenfolge

### 🔴 Background-Worker
- `run_evaluation()` existiert, aber wird nur manuell über `POST /proactivity/evaluate` aufgerufen
- Kein Scheduler (cron, APScheduler, Celery) für tägliche Evaluationen
- Kein separater Worker-Prozess

### 🔴 Logging & Monitoring
- Keine strukturierten Logs (nur stdlib logging)
- Kein Log-Aggregation oder persistente Log-Ausgabe
- Keine Metriken (z.B. Uvicorn-Performance)

### 🔴 Sicherheit & Betriebssicherheit
- Keine Authentifizierung (nur für vertrauenswürdige Netzwerke geeignet)
- DB-Passwort in compose.yaml hardcodiert
- Keine SSL/TLS für die API
- Keine Rate-Limiting oder CSRF-Schutz
- Datenbankport offen (auch wenn lokal gebunden)

### 🔴 Dokumentation & Prozesse
- Keine Betriebsdokumentation (Deployment, Upgrade, Backup, Restore)
- Kein Docker-Build-Prozess dokumentiert
- Keine Healthcheck-Definition
- Keine Rollback-Strategie

### 🟡 Datenbank-Persistierung
- Named Volume `postgres_data` existiert, aber:
  - Keine dokumentierte Backup-Strategie
  - Keine Validierung vor Upgrades
  - Keine Restore-Prozedur

---

## Implementierungs-Roadmap für Produktivbetrieb

### Phase 1: Docker-Basis (Mandatory)
1. **Dockerfile** für Hugo-App
   - Multi-stage Build (schlankes Prod-Image)
   - Non-root User
   - Healthcheck integriert
   
2. **compose.prod.yaml**
   - Web-Server (uvicorn, replicas-ready)
   - Background-Worker (APScheduler für tägliche Eval)
   - PostgreSQL (secrets via env-file)
   - Networks: internal DB-network, external API-network
   - Named volumes mit Backup-Flags

### Phase 2: Worker & Scheduler (Core)
1. **Worker-Einstiegspunkt** (worker.py)
   - APScheduler für `run_evaluation(trigger='scheduled')`
   - Konfigurierbare Häufigkeit (täglich um 06:00 UTC)
   - Fehlerbehandlung, Logging

2. **Migrations-Handling**
   - Idempotente Migrations-Runner
   - Vor App-Start prüfen
   - Rollback-Strategie dokumentieren

### Phase 3: Konfiguration & Secrets
1. **.env.prod.template**
   - Alle erforderlichen Variablen
   - Beispielwerte

2. **Umgebungsvariablen in Dockerfile/compose**
   - DATABASE_URL aus Service-Name konstruieren
   - OPENAI_API_KEY von außen
   - WORKER_ENABLED flag

### Phase 4: Dokumentation
1. **DEPLOYMENT.md**
   - Erste Installation auf Proxmox-VM
   - Start/Stop/Restart
   - Update-Prozedur
   - Backup/Restore
   - Troubleshooting

2. **docker-compose.prod.yaml Kommentare**
   - Jeder Service erklärt
   - Konfigurationsoptionen

---

## Implementierungs-Reihenfolge (diese Session)

1. ✅ Audit durchgeführt und dokumentiert
2. ⏭️ **Dockerfile** erstellen (Multi-stage, prodreif)
3. ⏭️ **requirements.txt** mit APScheduler erweitern
4. ⏭️ **Worker-Einstiegspunkt** (app/worker.py) implementieren
5. ⏭️ **Migration-Runner** (app/migrate.py) implementieren
6. ⏭️ **compose.prod.yaml** erstellen
7. ⏭️ **.env.prod.template** und **.dockerignore** erstellen
8. ⏭️ **DEPLOYMENT.md** schreiben
9. ⏭️ Lokal testen (Codespace): `docker compose -f compose.prod.yaml up`
10. ⏭️ Bestehende compose.yaml und Tests validieren (Kompatibilität)

---

## Codespace-Kompatibilität (MUSS erhalten bleiben)

Aktueller Workflow:
```bash
docker compose up -d db
.venv/bin/pip install -r backend/requirements.txt
cd backend && OPENAI_API_KEY=... uvicorn app.main:app --port 8000
```

**Nach der Umstellung darf folgendes NICHT brechen:**
- Die `compose.yaml` für lokale Entwicklung
- Der direkte Python-Start mit uvicorn
- Alle Tests (`pytest tests/`)
- Einzelne Services starten können (`docker compose up db`, `docker compose down`)
