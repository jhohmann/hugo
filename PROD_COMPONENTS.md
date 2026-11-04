# Hugo Produktions-Komponenten: Übersicht

**Stand:** 4. November 2026  
**Version:** 0.4.0

Diese Datei dokumentiert die neuen Komponenten, die für den Produktivbetrieb auf einer Proxmox-VM hinzugefügt wurden.

---

## Neue Dateien

### Docker & Containerisierung

- **[Dockerfile](/Dockerfile)** (67 Zeilen)
  - Multi-stage Build für schlankes Production-Image
  - Builder-Stage: Python-Dependencies installieren
  - Runtime-Stage: Non-root User, Health-Check, ~800 MB
  - Entrypoint: `uvicorn app.main:app` (Web-Server)
  - Alternativ: `python -m app.worker` (Background-Worker)

- **[.dockerignore](/.dockerignore)** (38 Zeilen)
  - Ausschließt VCS, Python-Cache, Tests, IDE-Dateien
  - Reduziert Image-Größe und Build-Zeit

- **[compose.prod.yaml](/compose.prod.yaml)** (230 Zeilen)
  - 3 Services: `db`, `web`, `worker`
  - PostgreSQL: internes Netzwerk, kein öffentlicher Port
  - Web-Server: lauscht auf `127.0.0.1:8000` (konfigurierbar)
  - Worker: Background-Service (ohne externen Port)
  - Health-Checks, Logging, Restart-Policy
  - Umgebungsvariablen für Konfiguration

- **[.env.prod.template](/.env.prod.template)** (43 Zeilen)
  - Template für Produktions-Umgebungsvariablen
  - DB_NAME, DB_USER, DB_PASSWORD (erforderlich!)
  - OPENAI_API_KEY (erforderlich!)
  - Konfigurierbar: WEB_PORT, LOG_LEVEL, SCHEDULER_HOUR/MINUTE

### Backend-Komponenten

- **[backend/app/worker.py](/backend/app/worker.py)** (130 Zeilen)
  - APScheduler-basierter Background-Worker
  - Täglich um 06:00 UTC (konfigurierbar): `run_evaluation(trigger='scheduled')`
  - Logging, Error-Handling, Graceful Shutdown
  - Einstiegspunkt: `python -m app.worker`

- **[backend/app/migrate.py](/backend/app/migrate.py)** (170 Zeilen)
  - Idempotente Migrations-Runner
  - Liest SQL-Dateien aus `backend/migrations/` in Reihenfolge
  - Nutzt `schema_version` Tabelle zur Verfolgung
  - Vor jedem App-Start ausgeführt (optional)

- **[backend/requirements.txt](/backend/requirements.txt)** (erweitert)
  - Neu: `apscheduler==3.10.4` für Scheduler

### Dokumentation

- **[DEPLOYMENT.md](/DEPLOYMENT.md)** (400+ Zeilen)
  - Vollständige Betriebsdokumentation
  - 1. Installation (erste VM-Einrichtung)
  - 2. Täglicher Betrieb (Start/Stop/Restart/Logs)
  - 3. Updates und Upgrades
  - 4. Backup & Restore
  - 5. Externe Erreichbarkeit (nginx Reverse-Proxy)
  - 6. Troubleshooting
  - 7. Monitoring & Alarmierung
  - 8. Sicherheitshinweise
  - 9. FAQ

- **[AUDIT_PROD_READY.md](/AUDIT_PROD_READY.md)** (150+ Zeilen)
  - Audit der bestehenden Hugo-Anwendung
  - Bestandteile vs. fehlende Komponenten
  - Implementierungs-Roadmap
  - Codespace-Kompatibilität (MUSS erhalten bleiben)

- **[README.md](/README.md)** (aktualisiert)
  - Getrennte Abschnitte: Entwicklung vs. Produktion
  - Link zu DEPLOYMENT.md
  - Übersicht neuer Komponenten

---

## Architektur (Produktiv)

```
┌─────────────────────────────────────────────────────────┐
│                    Proxmox VM (Debian)                  │
│                                                          │
│  Docker Daemon                                          │
│  ├─ hugo-db (PostgreSQL 17 + pgvector)                 │
│  │  └─ Internes Netzwerk, Named Volume                 │
│  ├─ hugo-web (FastAPI Server)                          │
│  │  └─ Ports: 127.0.0.1:8000 (configurable)            │
│  └─ hugo-worker (APScheduler, täglich 06:00 UTC)       │
│     └─ Kein externer Port                              │
│                                                          │
│  Optional: nginx (Reverse-Proxy)                        │
│  └─ Externe Erreichbarkeit via Domain                  │
│                                                          │
│  Netzwerke:                                             │
│  ├─ hugo_internal (nur DB ↔ Web/Worker)                │
│  └─ hugo_external (nur Web nach außen)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Deployment-Workflow

### Erste Installation

```bash
cd /opt/hugo
cp .env.prod.template .env.prod
# Editiere .env.prod: DB_PASSWORD, OPENAI_API_KEY
docker compose -f compose.prod.yaml build
docker compose -f compose.prod.yaml --env-file .env.prod up -d
curl http://localhost:8000/health
```

### Täglicher Betrieb

```bash
# Status
docker compose -f compose.prod.yaml ps

# Logs
docker compose -f compose.prod.yaml logs -f web

# Restart
docker compose -f compose.prod.yaml restart web

# Backup
docker exec hugo-db pg_dump -U hugo -d hugo > backup_$(date +%s).sql
```

### Update

```bash
git pull origin main
docker compose -f compose.prod.yaml build
docker compose -f compose.prod.yaml down
docker compose -f compose.prod.yaml --env-file .env.prod up -d
```

---

## Konfiguration

### .env.prod (kritisch)

| Variable | Default | Notwendig | Beispiel |
|----------|---------|-----------|----------|
| `DB_NAME` | `hugo` | Nein | `hugo` |
| `DB_USER` | `hugo` | Nein | `hugo` |
| `DB_PASSWORD` | — | **Ja** | `$(openssl rand -base64 32)` |
| `OPENAI_API_KEY` | — | **Ja** | `sk-proj-...` |
| `WEB_PORT` | `127.0.0.1:8000` | Nein | `0.0.0.0:8000` (extern) |
| `LOG_LEVEL` | `INFO` | Nein | `DEBUG`, `INFO`, `WARNING` |
| `SCHEDULER_HOUR` | `6` | Nein | `0`–`23` (UTC) |
| `SCHEDULER_MINUTE` | `0` | Nein | `0`–`59` (UTC) |

### Umgebungsvariablen (Dockerfile/compose)

Die folgenden Variablen werden automatisch gesetzt und sind normalerweise nicht konfigurierbar:

- `DATABASE_URL`: `postgresql://DB_USER:DB_PASSWORD@db:5432/DB_NAME`
- `PYTHONUNBUFFERED=1`: Unbuffered logging
- `PATH`: Enthält User-local pip-Binaries

---

## Migration-Handling

Migrationen werden **automatisch** beim Starten ausgeführt:

1. **DB-Container startet** → PostgreSQL wird initialisiert
2. **Schema + Migrationen werden in Reihenfolge ausgeführt**:
   - `schema.sql` (Basis-Tabellen)
   - `002_embeddings.sql` (pgvector für Memories)
   - `003_thread_embeddings.sql` (pgvector für Threads)
   - `004_temporal.sql` (Zeitfelder)
   - `005_proactivity.sql` (Evaluation & Suggestions)
   - `006_calendar.sql` (Calendar Actions)
3. **schema_version Tabelle** tracked bereits angewendete Migrationen
4. **Neue Migrationen** werden nur beim ersten Ausführen angewendet

**Wichtig:** Backup vor Update durchführen!

```bash
docker exec hugo-db pg_dump -U hugo -d hugo > backup_before_update.sql
git pull && docker compose -f compose.prod.yaml build
docker compose -f compose.prod.yaml --env-file .env.prod up -d
```

---

## Health-Checks

Beide Services haben automatische Health-Checks:

| Service | Check | Intervall | Retries |
|---------|-------|-----------|---------|
| `db` | `pg_isready -U hugo -d hugo` | 10s | 5 |
| `web` | `curl http://localhost:8000/health` | 30s | 3 |
| `worker` | (läuft permanent, kein Check) | — | — |

Fehlgeschlagene Health-Checks führen zu automatischem Restart (`restart: unless-stopped`).

---

## Logging

Alle Services nutzen `json-file` Logging-Driver mit Rotation:

| Service | Max Size | Max Files |
|---------|----------|-----------|
| `db` | 10 MB | 3 |
| `web` | 50 MB | 5 |
| `worker` | 30 MB | 3 |

Logs sind erreichbar via:
```bash
docker compose -f compose.prod.yaml logs [service]
docker compose -f compose.prod.yaml logs -f web  # Live-Logs
```

---

## Sicherheit

⚠️ **Hugo ist aktuell für vertrauenswürdige Netzwerke ausgelegt!**

- ✓ Keine öffentliche Datenbank (nur internes Netzwerk)
- ✓ Non-root User im Docker-Image
- ✓ Secrets via `.env.prod` (nicht in Git)
- ✗ Keine Authentifizierung (nur lokal oder hinter Reverse-Proxy)
- ✗ Keine Verschlüsselung (verwende nginx + SSL in Produktion)

Für externe Erreichbarkeit: nginx mit HTTP-Auth oder OAuth2-Proxy einsetzen.

---

## Kompatibilität

### ✅ Entwicklung (Codespace) bleibt funktionsfähig

- `compose.yaml` (alte Datei) funktioniert unverändert
- `docker compose up -d db` startet nur die Datenbank
- `python -m uvicorn app.main:app --port 8000` startet Web-Server lokal
- Alle Tests (`pytest tests/`) laufen ohne Änderungen

### ✅ Produktiv (Proxmox)

- `compose.prod.yaml --env-file .env.prod` läuft mit allen 3 Services
- Web + Worker aus demselben Docker-Image
- Automatische Migrationen beim Start
- Tägliche proaktive Auswertung (06:00 UTC)

---

## Nächste Schritte

### Später (nächste Sessions)

1. **Logging-Aggregation**: Zentrale Log-Sammlung (z.B. ELK, Loki)
2. **SSL/TLS**: nginx mit Let's Encrypt
3. **Authentifizierung**: HTTP-Auth oder OAuth2
4. **Monitoring**: Prometheus + Grafana
5. **Alerting**: E-Mail-Benachrichtigungen bei Fehlern
6. **Backup-Automation**: Tägliche, verschlüsselte Backups (z.B. Backblaze, S3)

---

**Siehe auch:** [DEPLOYMENT.md](./DEPLOYMENT.md) für vollständige Betriebsdokumentation.
