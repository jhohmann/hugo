# Hugo

Hugo ist ein proaktiver persönlicher Assistent für Zeitplanung, längerfristige
Vorhaben und Erinnerungen. Ein zentraler Agent verbindet Wissen und entscheidet,
welche Werkzeuge helfen. Python übernimmt Speicherung, Validierung, Zeitrechnung,
Scheduling und Freigabegrenzen. Sprache und Datumsdarstellung: Deutsch, Europe/Berlin.

**Stand: 6. November 2026. Es hat noch kein Deployment stattgefunden.** Entwickelt
wird in dieser lokalen Windows-Arbeitskopie mit PostgreSQL in Docker. Ziel ist
eine Docker Engine auf einem Proxmox-Gast; dieselbe Anwendung läuft dort als
Webserver und separater Worker. Frühere Codespace-Anleitungen bleiben als
Linux-Entwicklungsweg möglich. Betriebsbereitschaft auf Proxmox ist erst nach
einem dortigen Test bestätigt.

Diese Datei ist die gemeinsame Produkt-, Entwicklungs- und Betriebsdokumentation.
[AGENTS.md](AGENTS.md) enthält Produktziele und verbindliche Arbeitsregeln für Agenten.

## Inhalt

- [Lokal entwickeln](#lokal-entwickeln)
- [Passwort und Sitzungen](#passwort-und-sitzungen)
- [Konfiguration](#konfiguration)
- [Späterer Betrieb mit Docker auf Proxmox](#späterer-betrieb-mit-docker-auf-proxmox)
- [Updates und Datenbankmigrationen](#updates-und-datenbankmigrationen)
- [Backup, Restore und Rollback](#backup-restore-und-rollback)
- [Reverse-Proxy und HTTPS](#reverse-proxy-und-https)
- [Bedienung und Oberfläche](#bedienung-und-oberfläche)
- [Architektur und Datenmodell](#architektur-und-datenmodell)
- [API](#api)
- [Tests und Diagnose](#tests-und-diagnose)
- [Grenzen und Roadmap](#grenzen-und-roadmap)
- [Entwicklungsgeschichte und Dokumentationskonsolidierung](#entwicklungsgeschichte-und-dokumentationskonsolidierung)

## Lokal entwickeln

### Ordner und Zuständigkeiten

```text
backend/
  app/                 Anwendung und lokale Einstiegspunkte
    agent/             Zentraler Agent und proaktive Auswertung
    calendar/          Google-Zugriff und freizugebende Aktionen
    storage/           PostgreSQL-Zugriff und Embeddings
    tools/             Zeitrechnung und weitere Agentenwerkzeuge
    web/               UI-Routen, Templates und statische Dateien
  migrations/          Unveränderliche, versionierte SQL-Migrationen
  requirements.txt     Laufzeitabhängigkeiten für lokale App und Docker
  requirements-dev.txt Laufzeitabhängigkeiten plus Testwerkzeuge
tests/                 Automatisierte Tests; Konfiguration in pyproject.toml
scripts/               Update und ausdrücklich gestartete Diagnosewerkzeuge
```

Im Projektstamm liegen Dokumentation, Compose-/Docker-Konfiguration und lokale
Umgebungsdateien. `.venv`, Testcaches, Logs, Zugangsdaten und `backups/` sind lokale,
nicht versionierte Dateien. Der Docker-Build übernimmt nur die benötigten Quellen.
Neue Dateien gehören in die vorhandene fachliche Struktur; keine parallelen
Implementierungen oder Testskripte zwischen Anwendungscode ablegen.

Manuelle Diagnose vom Projektstamm mit der aktivierten virtuellen Umgebung:
`python scripts/check_embeddings.py` vergleicht Beispielsätze im Speicher, ohne
Datenbankeinträge anzulegen (beim ersten Lauf gegebenenfalls Modell-Download).
`python scripts/check_google_calendar.py` erhält das frühere persönliche
OAuth-Probeskript einschließlich seiner lokalen Anpassungen. Es benötigt separat
`google-auth-oauthlib` und `google-api-python-client`, liest `credentials.json`,
schreibt `token.json` und listet Termintitel. Es gehört nicht zum normalen Start
oder Testlauf; die Anwendung verwendet den OAuth-Weg unter `/ui/kalender`.

### Einrichtung und Start

Voraussetzungen: Python 3.12 oder neuer, Docker mit Compose v2, Git und ein
OpenAI-API-Schlüssel. Die aktuelle Windows-Umgebung nutzt Python 3.13.
Die virtuelle Umgebung und `.env` liegen im Projektordner. Zugangsdaten werden
nicht in Git oder in Docker-Images aufgenommen.

Einmalig im Projektordner, PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Copy-Item .env.example .env # nur wenn noch keine eigene .env existiert
docker compose up -d db
cd backend
..\.venv\Scripts\python.exe -m app.passwords
```

Das letzte Kommando fragt ein Passwort zweimal verdeckt ab und gibt einen
`HUGO_PASSWORD_HASH=scrypt-v1:...` aus. Die ganze Zeile in `.env` eintragen,
außerdem `OPENAI_API_KEY` setzen. Für lokales HTTP gilt `HUGO_COOKIE_SECURE=false`.
Die Entwicklungskonfiguration verbindet sich mit
`postgresql://hugo:hugo_dev@127.0.0.1:5432/hugo`. Explizites IPv4 vermeidet hier
das beobachtete Warten auf die nicht erreichbare IPv6-Adresse von `localhost`.

Normaler Start aus dem Projektordner:

```powershell
docker compose up -d db
cd backend
..\.venv\Scripts\python.exe -m app.dev
```

`app.dev` lädt die `.env` aus dem Projektordner, führt ausstehende Migrationen
aus und startet Uvicorn auf `127.0.0.1:8000` mit automatischem Code-Neuladen.
Bei einem Migrationsfehler startet der Webserver nicht. Browser:
[http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui). Beenden mit Strg+C.
`--port 8001`, `--no-reload` und `--env-file PFAD` sind optional.
`.env`-Änderungen erfordern einen vollständigen Neustart des Prozesses.
Schon gesetzte Prozessvariablen haben Vorrang vor der Datei; bei alten
PowerShell-`$env:...`-Werten ein neues Terminal verwenden.

Linux/macOS/Codespace, vom Projektordner:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
# .env anhand .env.example einrichten; bestehende .env nicht überschreiben
docker compose up -d db
cd backend
../.venv/bin/python -m app.dev
```

Für einen reinen Migrationslauf: im Ordner `backend` mit derselben Python-Umgebung
`python -m app.migrate`. Für einen direkten Uvicorn-Start, nachdem das Schema
aktualisiert wurde: `python -m uvicorn app.main:app --env-file ../.env --host
127.0.0.1 --port 8000 --reload`. Anders als `app.dev` migriert Uvicorn nicht.

Der tägliche Worker ist optional und wird **nicht** mit dem lokalen Webserver
gestartet. In einem zweiten Terminal im Ordner `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.worker
```

Er lädt ebenfalls die Projekt-`.env`. Standard: täglich 06:00 UTC, also 07:00
in der Berliner Winterzeit beziehungsweise 08:00 in der Sommerzeit.
Ohne Worker bleibt „Heute → Jetzt auswerten“ nutzbar. Eine Auswertung kann
kostenpflichtige OpenAI-Aufrufe auslösen.

## Passwort und Sitzungen

Ein gemeinsames Passwort, kein Benutzername und keine Benutzerverwaltung.
`python -m app.passwords` verlangt 12 bis 1024 Zeichen. Nur der gesalzene
scrypt-Hash wird konfiguriert. Das Klartext-Passwort gehört weder in Startbefehle
noch in Git. Ohne gültigen Hash bleibt die Anwendung gesperrt (HTTP 503).

Die Anmeldung unter `/ui/login` setzt ein zufälliges Token im HttpOnly-Cookie
`hugo_session`. PostgreSQL speichert nur dessen SHA-256-Hash. Ohne Häkchen gilt
ein Browser-Sitzungscookie, serverseitig höchstens 12 Stunden. Browser mit
Sitzungswiederherstellung können solche Cookies erhalten. „Angemeldet bleiben“
gilt 30 Tage ab Anmeldung, auch über Server- und Browser-Neustarts hinweg.
Es gibt keine gleitende Verlängerung.

Abmelden widerruft die aktuelle Sitzung sofort. Ein neu erzeugter Passwort-Hash
und Neustart aller Web-Prozesse machen alte Sitzungen ungültig. Abgelaufene
Sitzungen werden bei einer erfolgreichen Anmeldung bereinigt. Maximal zehn
Anmeldeversuche pro Minute insgesamt, über IPs und Prozesse hinweg; danach
HTTP 429 mit `Retry-After: 60`. Das Limit liegt in PostgreSQL.

Cookies verwenden SameSite=Lax und standardmäßig Secure. Für HTTPS
`HUGO_COOKIE_SECURE=true`, ausschließlich bei lokalem HTTP `false`. UI,
JSON-API, API-Dokumentation und Kalenderaktionen sind geschützt. Öffentlich
bleiben Anmeldung, statische Dateien und `/health`. Geschützte Antworten
werden mit `Cache-Control: no-store` ausgeliefert.

API-Skripte melden sich mit `POST /ui/login` und den Formfeldern `password`
sowie optional `remember=true` an, übernehmen das Cookie und verwenden es
für weitere Anfragen. POST/PATCH/PUT/DELETE benötigen einen passenden
`Origin`/`Referer`; Skripte ohne diese Header setzen `X-Hugo-Request: 1`, auch
beim Login. Ein fremder Origin wird trotz dieses Headers abgewiesen.
Cookies nicht loggen oder teilen. Swagger `/docs` funktioniert nach der
Browser-Anmeldung mit derselben Sitzung.

## Konfiguration

| Variable | Lokal / Docker / Bedeutung |
|---|---|
| `DATABASE_URL` | Optionaler vollständiger Verbindungsstring; hat Vorrang vor einzelnen DB-Feldern. Lokal siehe `.env.example`. In Docker normalerweise weglassen. |
| `DB_HOST`, `DB_PORT` | Ohne URL lokal `127.0.0.1`, `5432`; Docker setzt `db`, `5432`. Verbindungsaufbau ist zeitlich begrenzt. |
| `DB_NAME`, `DB_USER` | Standard jeweils `hugo`. |
| `DB_PASSWORD` | Nur lokal Standard `hugo_dev`; Docker verlangt ein eigenes Passwort. Einzelne Felder erlauben Sonderzeichen ohne URL-Encoding. |
| `OPENAI_API_KEY` | Schlüssel für den zentralen Agenten; erforderlich zum normalen App-Start. |
| `HUGO_PASSWORD_HASH` | Erzeugt durch `app.passwords`, für die Anmeldung erforderlich. |
| `HUGO_COOKIE_SECURE` | Standard `true`; lokales HTTP `false`. |
| `WEB_PORT` | Nur Docker: Standard `127.0.0.1:8000`, Format `[BIND_ADRESSE:]PORT`. |
| `LOG_LEVEL` | Standard `INFO`, unter anderem für Worker-Logging. Uvicorn hat eigene CLI-Logoptionen. |
| `SCHEDULER_HOUR`, `SCHEDULER_MINUTE` | Standard `6`, `0`, jeweils UTC (0–23 / 0–59). |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Optionaler Google-OAuth-Client; ohne ihn bleibt Kalender unverbunden. |
| `GOOGLE_REDIRECT_URI` | Exakt die im Google-Client registrierte Callback-URL; lokal `http://127.0.0.1:8000/ui/kalender/auth/callback`, später die HTTPS-Adresse. |
| `FORWARDED_ALLOW_IPS` | Docker/Uvicorn: nur tatsächliche Reverse-Proxy-IP oder dessen vertrauenswürdiges Netz; Standard `127.0.0.1`. |
| `HUGO_IMAGE` | Optionaler Docker-Image-Name, Standard `hugo:local`. Web, Worker und Migration nutzen dasselbe Image. |

Die lokale `compose.yaml` startet nur die Entwicklungsdatenbank mit festem
Entwicklungspasswort und bindet Port 5432 ausschließlich an IPv4-Loopback.
`.env.prod.template` ist die separate Vorlage für den späteren Docker-Betrieb.
Eine Änderung des DB-Passworts in einer Env-Datei ändert nicht das Passwort
einer bereits initialisierten PostgreSQL-Rolle; diese Änderung muss koordiniert
in der Datenbank erfolgen. Die Templates ersetzen keine vorhandenen Secrets.

## Späterer Betrieb mit Docker auf Proxmox

Ziel: Docker Engine und Compose v2 auf einem Proxmox-Gast, beispielsweise
Debian 12 oder Ubuntu 24.04 LTS. Frühere Planung: ungefähr 4–8 GB RAM und
20 GB Platte als Ausgangspunkt, keine gemessene Kapazitätszusage. Platzbedarf
für Python/Embedding-Modell, Daten, Images und Backups berücksichtigen.
Git, SSH/sudo und ausgehender Internetzugang werden benötigt. Installation
von Docker nach der [offiziellen Debian-Anleitung](https://docs.docker.com/engine/install/debian/);
Zugriff auf die Docker-Gruppe erlaubt weitreichende Kontrolle des Hosts.

Repository beispielsweise unter `/opt/hugo` klonen:

```bash
git clone https://github.com/jhohmann/hugo.git /opt/hugo
cd /opt/hugo
cp .env.prod.template .env.prod
chmod 600 .env.prod
```

DB-Passwort (zum Beispiel mit `openssl rand -hex 32`), OpenAI-Schlüssel,
Passwort-Hash und gegebenenfalls Google-/Proxy-Werte eintragen. Ohne lokale
Python-Installation lässt sich der Hash nach dem Build erzeugen:

```bash
docker build -t hugo:local .
docker run --rm -it --entrypoint python hugo:local -m app.passwords
```

Danach der erste Start:

```bash
docker compose --env-file .env.prod -f compose.prod.yaml up -d --build
docker compose --env-file .env.prod -f compose.prod.yaml ps -a
docker compose --env-file .env.prod -f compose.prod.yaml logs migrate web worker
curl --fail http://127.0.0.1:8000/health
```

Die Produktionsdatei ist eigenständig; **nicht** mit `compose.yaml` kombinieren.
Es gibt vier Services:

| Service | Aufgabe und Startbedingung |
|---|---|
| `db` | PostgreSQL 17 + pgvector, persistentes Volume `hugo_postgres_data`, kein veröffentlichter DB-Port. |
| `migrate` | Einmaliger Schemalauf nach gesundem PostgreSQL; Erfolg bedeutet Exitcode 0, danach beendet. |
| `web` | FastAPI/Uvicorn nach erfolgreicher Migration; Standardport nur auf Loopback. |
| `worker` | Separater APScheduler-Prozess nach erfolgreicher Migration; kein öffentlicher Port. |

Web und Worker haben zusätzlich zum internen DB-Netz ein Netzwerk für
ausgehenden Internetzugang: OpenAI, Google und initialer Embedding-Download.
Ein gemeinsames Volume `model_cache` hält die lokalen Modelle über Updates.
Das Multi-stage-Image verwendet Python 3.12, CPU-PyTorch, eine virtuelle
Umgebung und den Nutzer `hugo` ohne Root-Rechte. Die App braucht keine GPU.
Secrets, Dokumentation, Tests, Backups, lokale Umgebungen und Logs werden
vom Build-Kontext ausgeschlossen. Es gibt keinen Frontend-Build und kein CDN.

Die DB wird alle 5 Sekunden geprüft, der Webserver alle 30 Sekunden; der
Webserver hat 90 Sekunden Startfrist für Bibliotheksimporte. `/health` ist
ein Prozesscheck und prüft weder Anmeldung noch Datenbankbereitschaft.
Der Worker hat keinen HTTP-Healthcheck. `restart: unless-stopped` startet
beendete Prozesse neu; **ein Status „unhealthy“ allein startet einen
Container nicht automatisch neu**.

Logs verwenden Dockers `json-file`-Rotation: DB 10 MB × 3, Web 50 MB × 5,
Worker 30 MB × 3. Betriebskommandos (immer dieselbe Env-Datei verwenden):

```bash
docker compose --env-file .env.prod -f compose.prod.yaml logs -f web
docker compose --env-file .env.prod -f compose.prod.yaml logs --since 24h worker
docker compose --env-file .env.prod -f compose.prod.yaml restart web
docker compose --env-file .env.prod -f compose.prod.yaml stop web worker
```

`restart` lädt weder ein neues Image noch geänderte Container-Umgebungsvariablen;
dafür Container mit `up -d` neu erstellen. `down` ohne `--volumes` erhält
benannte Volumes. Nicht routinemäßig Volumes löschen oder `system prune --volumes`
für Logbereinigung verwenden. Docker Compose/Volumes sind projektbezogen;
ein anderer Projektname bedeutet andere Volumes und scheinbar leere Daten.

## Updates und Datenbankmigrationen

**Ja: Fast-Forward-Pull ist die richtige Basis.** Zusätzlich braucht ein Update
die neuen Abhängigkeiten beziehungsweise ein neues Image, Migrationen und
einen Neustart. Vor Schemaänderungen ein Backup anlegen; Web und Worker während
des Schemalaufs stoppen. `git pull --ff-only` bricht bei divergierter Historie
ab und erfindet keinen Merge. Es ersetzt weder Commit/Push der Entwicklungsarbeit
noch den Umgang mit uncommitteten Änderungen. Auf dem späteren Docker-Host
soll die Arbeitskopie sauber bleiben; Secrets und Daten liegen außerhalb von Git.

### Lokal

Webserver und optionalen Worker mit Strg+C stoppen, Daten sichern, dann im Projektordner:

```powershell
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'Git-Update fehlgeschlagen' }
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Abhängigkeiten konnten nicht installiert werden' }
docker compose up -d db
if ($LASTEXITCODE -ne 0) { throw 'Datenbankstart fehlgeschlagen' }
cd backend
..\.venv\Scripts\python.exe -m app.dev
```

Der letzte Befehl übernimmt die Migration vor dem Start. Einen zusätzlich
benutzten Worker anschließend ebenfalls neu starten. Unter Linux entsprechend
`.venv/bin/python` nutzen und die Befehle bei Fehlern abbrechen.

### Docker-Host

Der Updateablauf ist in [scripts/update.sh](scripts/update.sh) zusammengefasst:

```bash
bash scripts/update.sh
```

Das Skript verlangt eine saubere getrackte Arbeitskopie, führt `git pull --ff-only`
aus, baut das gemeinsame Image, prüft die DB, stoppt Web/Worker, schreibt einen
PostgreSQL-Dump nach `backups/`, führt den Migrationsservice aus und startet
Web/Worker mit dem neuen Image. Die Datenbank und ihre Volumes bleiben bestehen.
Bei Build-Fehlern läuft die alte App weiter. Nach einem Migrationsfehler bleiben
die Apps gestoppt; den Fehler prüfen, nicht mit einem alten Image blind starten.
Es gibt keinen automatischen Daten-Rollback.

### Schema und zukünftige Änderungen

Die Entwicklungsschritte `schema.sql` und Migrationen 002–007 sind vor dem
ersten Deployment in **[001_initial.sql](backend/migrations/001_initial.sql)**
zusammengeführt. Diese Datei ist die einzige Definition der Ausgangsbasis.
Sie erstellt auch pgvector, Vektorspalten/-indizes, Zeitfelder, Vorschläge,
Kalender- und Authentifizierungstabellen. Die vollständige bestehende lokale
Datenbank kann ohne Löschen ihrer Inhalte übernommen werden. Unvollständige
alte Schemata werden nicht stillschweigend als aktuell markiert.

Der Migrationsrunner funktioniert gleich bei leerer und vorhandener Datenbank.
`schema_version` speichert Nummer, Dateiname, SHA-256-Prüfsumme und Zeitpunkt.
Eine PostgreSQL-Advisory-Lock serialisiert gleichzeitige Läufe. Jede Datei und
ihr Versionsvermerk werden gemeinsam in einer Transaktion ausgeführt. Ein Fehler
rollt diese Datei zurück und liefert einen von null verschiedenen Exitcode.
Früher in demselben Lauf abgeschlossene Migrationen bleiben angewendet.

Ab jetzt die angewendete Ausgangsbasis **nicht mehr ändern**. Neue Änderungen
werden `002_<name>.sql`, `003_<name>.sql` usw. Bereits angewendete Dateien
werden weder geändert noch umbenannt, gelöscht oder in die Vergangenheit
einsortiert. Fehlende/geänderte Dateien und eine zum Checkout neuere Datenbank
blockieren den Lauf. CRLF und LF erhalten dieselbe Prüfsumme. SQL-Dateien dürfen
keine eigenen COMMIT/ROLLBACK-Kommandos und keine nichttransaktionalen Operationen
wie `CREATE INDEX CONCURRENTLY` enthalten; solche Änderungen brauchen einen
gesondert entworfenen Ablauf.

Compose mountet keine Init-SQL-Dateien mehr in PostgreSQL. Dadurch laufen
Erstinstallation und spätere Updates über denselben Runner; die frühere
Beschränkung von `/docker-entrypoint-initdb.d/` auf leere Volumes entfällt.

## Backup, Restore und Rollback

Ein PostgreSQL-Dump ist die Sicherung; ein Git-Checkout enthält keine persönlichen
Daten. Sicherungen enthalten außerdem Google-Tokens und Sitzungshashes und
gehören geschützt beziehungsweise verschlüsselt abgelegt. Regelmäßig eine
Wiederherstellung in eine getrennte Datenbank testen. Lokale Entwicklung und
spätere Produktion haben getrennte Datenbestände. Ein Umzug erfolgt bei Bedarf
bewusst durch Dump/Restore, nicht durch Git oder das Kopieren eines laufenden Volumes.

Manuelles Backup auf dem Linux-Docker-Host, im Projektordner:

```bash
mkdir -p backups
chmod 700 backups
umask 077
docker compose --env-file .env.prod -f compose.prod.yaml exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/hugo.dump
```

Unter Windows das Binärformat nicht durch ältere PowerShell-Textumleitungen
leiten. Stattdessen im Entwicklungscontainer erzeugen und danach kopieren:

```powershell
docker compose exec -T db pg_dump -U hugo -d hugo -Fc -f /tmp/hugo-backup.dump
if ($LASTEXITCODE -ne 0) { throw 'Backup fehlgeschlagen' }
$dbContainer = docker compose ps -q db
New-Item -ItemType Directory -Force backups | Out-Null
docker cp "${dbContainer}:/tmp/hugo-backup.dump" backups/hugo-backup.dump
```

Erst nach erfolgreicher Sicherung aktualisieren. Dateinamen je Sicherung mit
Datum versehen; das Update-Skript tut dies automatisch. Eine tägliche Sicherung
um 02:00 per Cron und mindestens sieben Tage Aufbewahrung waren die ursprüngliche
Betriebsplanung. Diese Automatisierung ist noch einzurichten; eine separate
Aufbewahrungsregel darf ausschließlich das eigene Backup-Verzeichnis betreffen.
Backups außerhalb des Docker-Hosts halten, Speicherplatz und Erfolg überwachen.

Restore zunächst in eine **neue** Datenbank, ohne die funktionierende zu löschen:

```bash
docker compose --env-file .env.prod -f compose.prod.yaml exec -T db sh -c \
  'createdb -U "$POSTGRES_USER" hugo_restore'
docker compose --env-file .env.prod -f compose.prod.yaml exec -T db sh -c \
  'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d hugo_restore' < backups/hugo.dump
```

Für Entwicklung entsprechend `docker compose` ohne Produktionsdatei nutzen.
Unter Windows den Dump per `docker cp` in den Container kopieren und dort
`pg_restore` mit Dateipfad ausführen. Anschließend passenden Code-Stand,
Schema-Version und Daten prüfen; erst dann mit gestoppten Web-/Worker-Prozessen
auf die restaurierte Datenbank umschalten. Die ursprüngliche Datenbank behalten,
bis der Restore bestätigt ist. Der Dump enthält auch `schema_version`.

Rollback bedeutet bei inkompatiblen Schemata: passender früherer Code-/Image-Stand
**und** der vor dem Update gesicherte Datenstand. Nur ein altes Image zu starten
ist kein verlässlicher Datenbank-Rollback. Zwischenzeitliche Änderungen müssen
vor einer Wiederherstellung gesichert und gegebenenfalls separat übernommen werden.

## Reverse-Proxy und HTTPS

Für Zugriff außerhalb des lokalen Rechners HTTPS vorsehen. Beispiel: nginx
auf dem Docker-Host, Domain `hugo.example.com`, Backend an `127.0.0.1:8000`.
Port 5432 nicht veröffentlichen. Firewall gegebenenfalls für SSH 22 und HTTP/HTTPS
80/443 freigeben. Einen extern gebundenen Backend-Port nur für den Proxy erreichbar machen.

```nginx
server {
    listen 80;
    server_name hugo.example.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }
}
```

Auf Debian nginx sowie `certbot`/`python3-certbot-nginx` installieren, die
Site aktivieren, `nginx -t` prüfen und beispielsweise `certbot --nginx -d
hugo.example.com` für HTTPS verwenden. Das HTTP-Beispiel allein ist noch kein
TLS-Setup. Danach `HUGO_COOKIE_SECURE=true` setzen und die Google-Callback-URL
auf HTTPS umstellen. Uvicorn muss den tatsächlichen Proxy-Absender über
`FORWARDED_ALLOW_IPS` kennen. Bei Host-nginx vor Docker kann das die Bridge-
Gateway-IP statt `127.0.0.1` sein. Kein pauschales Vertrauen in fremde
Forwarded-Header: falsches Schema/Host führt auch zu HTTP 403 bei Formularen.
Ein `/ws`-Proxyblock ist derzeit nicht erforderlich, Hugo hat keine WebSockets.

## Bedienung und Oberfläche

Die Oberfläche ist mit FastAPI/Jinja2 serverseitig gerendert, formbasiert und
ohne AJAX, Frontend-Build oder externe CDN-Abhängigkeiten. `/ui` führt nach
Anmeldung zu „Heute“. Inhaltliche Änderungen passieren über den Chat;
die übrigen Ansichten dienen der Übersicht und gezielten Bestätigung.

| Ansicht | Funktionen |
|---|---|
| Chat `/ui/chat`, `/ui/chat/{id}` | Neue/fortgesetzte Unterhaltung, vollständiger Verlauf, 50 jüngste Unterhaltungen mit erster Nutzernachricht als Vorschau; Ladezustand „Hugo denkt nach …“; Entwurf bleibt bei Agentenfehler erhalten. POST leitet zur Unterhaltung weiter. |
| Heute `/ui/heute` | Offene Vorschläge mit Grund, P1–P5, Vorhaben-Link, Datum und Hinweisen wie „heute“, „morgen“, „in N Tagen“, „seit N Tagen“. Bestätigen → `confirmed`, zurückstellen → `deferred`, verwerfen → `dismissed`. Zurückgestellte Vorschläge sind einklappbar. Letzter Evaluationslauf und „Jetzt auswerten“ sind sichtbar. |
| Vorhaben `/ui/threads` | Gruppen Aktiv, Wartet, Idee; Erledigt/Archiviert einklappbar. Titel, nächster Schritt, Priorität, Ereigniszeitraum, „handeln bis“ und harte Deadline. |
| Vorhaben-Detail `/ui/threads/{id}` | Beschreibung, Originalzeittext, Zeitfelder, Status/Priorität, Erstell-/Änderungszeit in Berlin und zugehörige Vorschläge; Aktionen erhalten das Rücksprungziel. |
| Kalender `/ui/kalender` | Google-Verbindung herstellen/trennen, Kalenderstatus, vorgeschlagene Aktionen, Konflikte und vergangene Aktionen einsehen; Schreiben erst nach expliziter Bestätigung. |

Das Abrufen offener Vorschläge markiert sie von `pending` nach `surfaced`.
Bestätigung eines Vorschlags ist nicht automatisch die Genehmigung einer
beliebigen externen Aktion. Kalender-Schreibaktionen besitzen einen eigenen
Freigabeweg. Vorschläge werden nicht automatisch bei jedem Seitenaufruf erzeugt:
dazu muss eine manuelle oder geplante Auswertung laufen.

Minimal-JavaScript ergänzt Ladeanzeigen (`data-loading-text`), Bestätigungsdialoge
(`data-confirm`), Scrollen ans Nachrichtenende, Enter-zum-Senden und
Shift+Enter für Zeilenumbrüche. Ohne JS bleiben Formulare nutzbar; es fehlen
Ladeanzeige, Bestätigungsdialog und Enter-Komfort. Die Unterhaltungsliste wird
auf kleinen Bildschirmen eingeklappt. Keine obligatorische Rückfrage nach jeder Antwort.

Responsive CSS: Chat-Sidebar am Desktop, einspaltig bis 760 px, begrenzte
Nachrichtenbreite, umbrechende Vorhaben-Metadaten. Light/Dark Mode folgt
`prefers-color-scheme`. Semantische Elemente, ARIA-Labels/-Navigation,
`aria-live`, unsichtbare Feldbeschriftungen und Text zusätzlich zu Farben
unterstützen Tastatur- und Screenreader-Nutzung. Hohe Prioritäten ab P4 und
überfällige Daten werden hervorgehoben; Details nutzen unter anderem `<dl>`
und `<details>`. Die Listen haben begrenzte Ergebnismengen, aber keine vollständige
Blätterfunktion. Einklappen ist keine serverseitige Lazy-Loading-Funktion.

Designfarben aus `style.css`: Hell Hintergrund `#f6f7f9`, Fläche `#ffffff`,
Text `#1c1e21`, Akzent `#2563eb`, Gefahr `#b91c1c`, OK `#15803d`, Warnung
`#b45309`; dunkel Hintergrund `#14171b`, Fläche `#1d2127`, Text `#e5e7eb`.
CSS ist eine lokale Datei, nicht inline; Browser laden ein kleines zusätzliches JS.

## Architektur und Datenmodell

Stack: Python/FastAPI, OpenAI Responses API (`gpt-5-mini`), PostgreSQL 17
(`pgvector/pgvector:pg17`), psycopg/pgvector.psycopg, Jinja2, APScheduler 3.10.4.
Lokale normalisierte Embeddings: `intfloat/multilingual-e5-small`, 384 Dimensionen,
`query:`-/`passage:`-Präfixe, HNSW mit Cosinus-Abstand. Modelle werden beim ersten
Bedarf geladen/heruntergeladen und danach pro Prozess gehalten; der gemeinsame
Docker-Cache vermeidet erneute Downloads, nicht den Speicherbedarf je Prozess.

| Datei/Modul | Verantwortung |
|---|---|
| `backend/app/main.py` | FastAPI-JSON-Endpunkte, UI-/Static-Einbindung. |
| `backend/app/chat_service.py` | Gemeinsamer Chatdienst für API und UI, Persistenz, Fehlerbehandlung. |
| `backend/app/agent/assistant.py` | Zentraler Systemprompt und begrenzte Tool-Calling-Schleife. |
| `backend/app/agent/evaluation.py` | Proaktivitätsbewertung über dieselbe Schleife, eingeschränkte Werkzeuge. |
| `backend/app/storage/` | Datenbank, Embeddings, Erinnerungen, Vorhaben, Vorschläge, Google-Tokens, Kalenderaktionen, Auth-Sitzungen. |
| `backend/app/tools/dates.py` | Berlin-Zeitkontext und zuverlässige Datumsarithmetik (`compute_date`). |
| `backend/app/calendar/` | Google-REST/OAuth-Client, reine Zeit-/Konfliktlogik, freigegebene Ausführung. |
| `backend/app/web/routes.py`, `formatting.py` | UI-Routen und deutsche Formatierung; dieselben Storage-/Service-Funktionen wie API, keine parallele Fachlogik. |
| `backend/app/web/templates/` | `base`, `chat`, `heute`, `threads`, `thread_detail`, `thread_row`, `kalender`, `login`, `error`. |
| `backend/app/web/static/` | `style.css`, `app.js`, ausgeliefert unter `/static`. |
| `backend/app/auth.py`, `passwords.py` | Gemeinsame Zugriffsschranke, Login/Logout, Hash-Erzeugung. |
| `backend/app/config.py`, `dev.py` | Gemeinsame Konfiguration und lokaler Start. |
| `backend/app/migrate.py`, `backend/migrations/` | Versionierter, transaktionaler Schemalauf und konsolidierte Ausgangsbasis. |
| `backend/app/worker.py` | Separater täglicher Auswertungslauf, ein Job je Prozess, keine konkurrierenden Instanzen desselben Jobs. |
| `Dockerfile`, `.dockerignore`, `compose*.yaml` | Gemeinsames Image sowie getrennte lokale/Host-Konfiguration. |

`conversations` und `messages` speichern Unterhaltungen und Nachrichten.
`memories` enthält Inhalt, Kategorie, Status `proposed`/`confirmed`/`outdated`,
Gültigkeit, Quellnachricht, Zeitstempel und Vektor. Exakte Duplikate werden
unterdrückt; `update_memory` aktualisiert bisher nur `proposed`-Erinnerungen.

`threads`: Titel, Beschreibung, Status `proposed`/`active`/`waiting`/`completed`/
`archived`, Priorität, nächster Schritt und Zeitstempel. `thread_memories` und
`thread_messages` verknüpfen Wissen und Quellnachrichten. Die fünf Agentenwerkzeuge
`search_threads`, `list_threads`, `get_thread`, `create_thread`, `update_thread`
verwenden gezielt IDs aus vorherigem Suchen/Lesen; Updates verändern nur
explizit mitgegebene Felder. Ideen werden `proposed`, konkrete Vorhaben `active`.

Zeitfelder unterscheiden:

- `event_start`/`event_end`: DATE für Punkt oder inklusiven Zeitraum; Ende braucht
  Anfang und darf nicht davor liegen.
- `time_precision`: `exact` oder `approximate`; `time_text` bewahrt die ursprüngliche Angabe.
- `deadline`: TIMESTAMPTZ für eine vom Nutzer genannte harte Frist, nie aus vagen Angaben erfunden.
- `act_by`: DATE für Hugos Handlungsempfehlung beziehungsweise Vorlauf.

Offene Vorhaben werden nach `COALESCE(act_by, event_start, deadline)` geordnet.
Datumsarithmetik unterstützt Tage/Wochen/Monate/Jahre, Monatsenden und Schaltjahre.
Aktuelle Uhrzeit, Datum und deutscher Wochentag in Europe/Berlin werden bei jedem
Agentenaufruf injiziert. Fehlende Referenzdaten führen bei relativen Änderungen
zu einer gezielten Rückfrage. Naive Deadline-Datetimes werden bislang als UTC
interpretiert; gesetzte Datumsfelder lassen sich über das Tool nicht auf null löschen.

`evaluation_runs` protokolliert `manual`/`scheduled`, `running`/`completed`/
`failed`, berücksichtigte Vorhaben, neue Vorschläge, Fehler und Laufzeiten.
`suggestions` enthält Vorhaben-/Laufbezug, Text, Grund, Priorität 1–5,
Handlungsdatum, Zustellung `pending`/`surfaced` und Bearbeitung
`open`/`confirmed`/`deferred`/`dismissed`. Die Auswertung betrachtet offene
Vorhaben, jüngste Erinnerungen und offene/zurückgestellte Vorschläge. Sie nutzt
lesende Werkzeuge plus `create_suggestion`, keinen zweiten Agenten. Exakt
normalisierte Inhalte werden pro Vorhaben über Läufe und Bearbeitungsstatus hinweg
dedupliziert. Umformulierungen können dennoch erneut erscheinen.

Kalender: Google Calendar ist die Quelle tatsächlicher Termine, Hugos Vorhaben
bilden die getrennte Planungsebene. `google_credentials` hält genau eine
OAuth-Verbindung, `google_oauth_states` die einmaligen States.
`calendar_actions` speichert vorgeschlagene Create/Update/Delete-Aktionen mit
Payload, Snapshot, Status `pending`/`confirmed`/`rejected`/`executed`/`failed`/
`conflict`, Ergebnis/Fehler und Quellnachricht. `calendar_action_log` bewahrt
die Historie auch für Löschungen. Access-/Refresh-Tokens bleiben in PostgreSQL
und werden nicht ans Modell übergeben. Bestätigung erfolgt ausschließlich über
die freigegebenen UI-/API-Wege. Konflikte verlangen erneute Bestätigung;
deterministische Event-IDs verhindern doppelte Neuanlagen bei Wiederholung.
Hugo-Termine erhalten `[H]` und einen Änderungsverlauf. Zeitzonen und Googles
exklusive Enddaten ganztägiger Termine werden berücksichtigt; das ersetzt
noch keine umfassenden Tests für alle Wiederholungs-/Abbruchfälle.

`auth_sessions` und `auth_login_limit` enthalten Sitzungshashes, Passwortversion,
Ablauf und den gemeinsamen Anmeldezähler. `schema_version` enthält ausschließlich
die Migrationshistorie. Frühere Dokumente erwähnten fälschlich Tabellen
`suggestions_run_mapping` oder `calendar_sync_log`; diese gehören nicht zum Schema.

## API

Nach Anmeldung: `/docs` (Swagger), `/redoc`, `/openapi.json`. UI-Routen sind mit
`include_in_schema=False` ausgeblendet. Die UI ruft gemeinsame Python-Dienste auf,
nicht intern die JSON-HTTP-API. Die bestehenden fachlichen APIs bleiben erhalten.

| Methode/Route | Zweck |
|---|---|
| `GET /` | Name, Version und Status als JSON, geschützt. |
| `GET /health` | Öffentlicher Prozesscheck. |
| `POST /chat` | `message` und optionale `conversation_id`; persistiert und ruft Agenten. |
| `GET /conversations` | Jüngste Unterhaltungen mit Vorschau. |
| `GET /conversations/{id}/messages` | Nachrichten einer Unterhaltung. |
| `GET /memories` | Lesende Entwicklungs-/Inspektionsansicht. |
| `GET /threads` | Vorhaben, optionaler `status`-Filter. |
| `POST /proactivity/evaluate` | Manueller Auswertungslauf. |
| `GET /proactivity/runs` | Audit der Auswertungen. |
| `GET /suggestions` | `status`-/`delivery`-Filter; zurückgegebene ausstehende Vorschläge werden `surfaced`. |
| `PATCH /suggestions/{id}` | `confirmed`, `deferred` oder `dismissed`. |
| `GET /calendar/status` | Konfiguration/Verbindung, gegebenenfalls Kalenderliste ohne Tokens. |
| `GET /calendar/actions` | Aktionen, optional `status`. |
| `POST /calendar/actions/{id}/confirm` | Explizite Freigabe und Ausführung; optional `force` nach geprüftem Konflikt. |
| `POST /calendar/actions/{id}/reject` | Aktion ablehnen. |
| `POST /calendar/disconnect` | Google-Verbindung trennen. |

UI-POSTs: `/ui/chat`, `/ui/evaluate`, `/ui/suggestions/{id}`,
`/ui/calendar-actions/{id}`, `/ui/kalender/disconnect`, `/ui/login`, `/ui/logout`.
OAuth-GETs: `/ui/kalender/auth/start` und `/ui/kalender/auth/callback`.
Ungültige Filter/Aktionen ergeben 400, fehlende Objekte 404, Kalenderkonflikte 409,
externe Servicefehler gegebenenfalls 502. Ohne API-Sitzung 401; UI leitet zur
Anmeldung. Fehler beim Datenbankzugriff werden ohne Zugangsdaten ausgegeben.

Die meisten JSON-Listen begrenzen `limit` auf 1–500. API-Exporte für Erinnerungen
und Vorhaben sind damit möglich, aber kein vollständiges Backup großer Bestände;
`limit=1000` umgeht diese Grenze nicht. Für vollständige Sicherungen `pg_dump` nutzen.

## Tests und Diagnose

Testabhängigkeiten: `python -m pip install -r backend/requirements-dev.txt`.
`python -m pytest` findet über `pyproject.toml` ausschließlich `tests/` und setzt
den Importpfad auf `backend`. Diagnosewerkzeuge werden dabei nicht ausgeführt.

Im Projektordner:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Tests setzen einen Dummy-OpenAI-Key, rufen aber kein echtes Modell auf, sofern
Storage/Agent gemockt werden. Web-/Tool-/Datums-/Evaluations-Tests benötigen keine
OpenAI-Verbindung. Datenbanktests überspringen sich ohne PostgreSQL; semantische
Storage-Tests können das lokale Embedding-Modell beim ersten Lauf herunterladen.
Nicht gegen eine produktive Datenbank testen. Auth-Tests arbeiten in temporären
Schemas, Migrationstests in eigens angelegten Datenbanken; dafür braucht der
Testnutzer CREATE-DATABASE-Rechte. Testobjekte werden anschließend entfernt.

Gezielt Start/Update/Auth prüfen:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_migrations.py tests/test_config.py tests/test_worker.py tests/test_auth.py tests/test_auth_storage.py tests/test_web.py -q
```

Migrationstests prüfen leere DB, Übernahme vorhandener Daten, wiederholte und
parallele Läufe, Prüfsummen, ältere Checkouts, CRLF/LF und atomaren Fehler-Rollback.
Auth-Tests prüfen echte HTTP-Routen mit PostgreSQL, Sitzungsablauf, Wiederverwendung,
Widerruf und paralleles Versuchslimit; Testpasswörter gelten nur im Test.

Verifiziert am 06.11.2026: **95 Tests bestanden**, einschließlich des optionalen
Docker-Tests (`HUGO_DOCKER_SMOKE=1`, zuvor `docker build -t hugo:local .`).
Dieser startet ein isoliertes Compose-Projekt mit Testzugängen, prüft Anmeldung,
Modellcache-Schreibrechte und ausgehenden Worker-Zugriff sowie Sitzungserhalt nach
Migration und Neuerstellen der Container. Seine Testvolumes werden danach entfernt.
Die lokale Datenbank wurde vor der Übernahme gesichert; alle Inhalte der 14
Anwendungstabellen waren danach unverändert. Auch `app.dev` wurde mit echter
Migration und HTTP-Healthcheck gestartet; der bestehende Entwicklungsserver
antwortet weiterhin auf Port 8000. Proxmox, der vollständige Git-Pull-
Updateablauf und echte Google-/OpenAI-Aufrufe waren nicht Teil dieses Tests.

Anschließende Strukturprüfung: 129 Tests bestanden, der optionale Docker-Test
übersprungen. Die beiden bestehenden Integrationsmodule `test_thread_storage.py`
und `test_suggestions.py` wurden dabei ausdrücklich ausgeschlossen, da sie die
konfigurierte Datenbank verwenden. Manuelle Skripte wurden auf nebenwirkungsfreien
Import geprüft; echte Kalenderabfragen und Modell-Downloads wurden nicht ausgelöst.
Das bereinigte Docker-Image wurde erfolgreich gebaut und ohne Netzwerk geprüft:
Anwendung importierbar, Migration enthalten, `pytest` nicht installiert.

| Problem | Prüfung / Abhilfe |
|---|---|
| Login hängt | DB läuft? `DATABASE_URL` lokal auf `127.0.0.1`; Docker nutzt Service `db`. Verbindungstimeout und Logs prüfen. |
| Zurück auf Login nach korrektem Passwort | Bei lokalem HTTP Secure-Cookie deaktivieren; nicht zwischen `localhost` und `127.0.0.1` wechseln. |
| HTTP 403 nach Proxy | Host/Origin und `X-Forwarded-Proto`, vertrauenswürdige Proxy-IP prüfen. |
| HTTP 503 / Anmeldung nicht eingerichtet | Gültigen Hash konfigurieren; vollständigen Prozessneustart statt nur Datei-Reload. |
| Alte Env-Werte bleiben | Neues Terminal; Prozessvariablen haben Vorrang. Docker `up` statt bloß `restart` bei Env-Änderung. |
| Port 8000 belegt | Alten eigenen Server beenden oder lokal `--port`, in Docker `WEB_PORT` ändern. |
| Migration fehlgeschlagen | `migrate`-Logs und Exitcode prüfen. Keine Historienzeilen löschen, um Prüfsummenfehler zu übergehen. |
| Kein Vorschlag | Manuell „Jetzt auswerten“ oder Worker starten; `SCHEDULER_HOUR/MINUTE` sind UTC. Fehlgeschlagene Läufe stehen in `evaluation_runs`. |
| Worker ohne API-Zugriff | Ausgehendes Netz und API-Key prüfen; genau einen Worker betreiben. |
| Langsamer erster Start | Python-/Torch-Import und initialer Modell-Download können dauern. Docker-Cache und RAM prüfen. |
| Chat leer/unvollständig | Modellstatus und Tokenverbrauch prüfen; `gpt-5-mini` kann das Ausgabelimit für Reasoning verbrauchen. Low reasoning und Diagnose beibehalten. |
| Datenbank/Platte voll | Dump sichern, tatsächliche DB-/Volume-/Log-Größen prüfen, gegebenenfalls `vacuumdb`; nicht vorschnell Volume löschen. |

Docker-Diagnose: `ps -a`, `logs --since 24h web worker db migrate`, `/health`,
anschließend eine echte Anmeldung. Logs und Tokenverbrauch auswerten, keine
Schlüssel/Tokens protokollieren. Support: [GitHub Issues](https://github.com/jhohmann/hugo/issues).

## Grenzen und Roadmap

Bereits vorhanden: zentraler Agent, Erinnerungen/Vorhaben, Zeitkontext,
manuelle und geplante Auswertung, serverseitige Oberfläche, Google-Kalendercode,
Passwort-Anmeldung. Das ist noch kein Beweis für zuverlässige unbeaufsichtigte
Assistenz oder ein geprüftes Proxmox-Deployment.

Weiter offen, in Produktpriorität:

1. Zeitplanung: Abhängigkeiten zwischen Vorhaben, Blocker/Wartegründe, nächster
   Prüftermin, Quellen/Vertrauen von Zeitangaben, sinnvolle Vorbereitungsfenster.
2. Proaktivität: reale tägliche Läufe und nützliche Interventionen beobachten,
   semantische Wiederholungen/dismissed-Themen besser unterdrücken, Benachrichtigungs-
   ermüdung vermeiden. Zustellkanal noch entscheiden: Digest beim nächsten Chat
   oder Push. Kein E-Mail-Lesen gewünscht.
3. Kalender: Integration und Konfliktprüfung umfassender testen, Verfügbarkeit
   gezielt in Auswertungen einbeziehen; Wiederholungen, Zeitzonen, ganztägige und
   abgesagte Termine prüfen. Interne Planung bleibt getrennt von echten Terminen.
4. Aktionen: bestehende Kalender-Freigaben zu einem nachvollziehbaren allgemeinen
   Vorschlags-/Genehmigungs-/Ausführungssystem ausbauen, idempotent und auditierbar.
5. Betrieb: erster Proxmox-Smoke-Test, TLS/Proxy, Backup-Restore und Update-Rollback,
   Monitoring/Alarmierung und API-Verbrauch prüfen. Aggregierte Logs (z.B. Loki/ELK),
   Prometheus/Grafana, verschlüsselte externe Backups (z.B. S3/Backblaze) und
   systemd/E-Mail-Alarme sind mögliche spätere Ergänzungen, noch nicht eingerichtet.

Ein Nutzer und ein Worker; keine getestete Hochverfügbarkeit, Load-Balancer-
Installation, Multi-Tenancy oder getrennten Arbeits-/Privatkonten. Work/private
Trennung ist langfristig erwünscht. Keine CI/CD-Pipeline, Registry oder Kubernetes
erforderlich, solange kein konkreter Bedarf besteht. Image-Größe, Build-Cache
und Kaltstart sind später optimierbar. Aktuell werden viele Paketversionen nicht
fest gepinnt; ein Rebuild ist deshalb kein bitgenau reproduzierbarer Release.

Weitere bekannte Grenzen: Datumsfelder nicht auf null löschbar, Erinnerungsupdates
nur für `proposed`, semantische Duplikate/Konflikte, fehlende automatische
Gesprächstitel, begrenzte Listen ohne Paging, kein Push/Realtime. Optionale UI-Ideen
aus der frühen Planung: Titel, Editor für Beschreibungen, Export/Druck; sie sind
gegen die Priorität proaktiver Hilfe abzuwägen, keine zugesagten nächsten Features.

API-Kosten hängen von Nutzung, Modell und Kontext ab; die alte Schätzung
„unter 1 USD/Monat“ war nicht gemessen und ist keine Zusage. Relevanter Kontext
verlässt bei Modellaufrufen das lokale System. Datenschutz-/Aufbewahrungsanforderungen
und Anbieterbedingungen sind für die eigenen Daten zu prüfen; diese Dokumentation
stellt keine Datenschutz- oder Compliance-Zusage dar.

## Entwicklungsgeschichte und Dokumentationskonsolidierung

| Zeitpunkt | Ergebnis / aufbewahrtes Wissen |
|---|---|
| 02.–03.11.2026 | Persistenter Chat, zentrale modellgesteuerte Memory-Tools. Norwegen-Monatsänderung aktualisierte dieselbe Erinnerung. Eine separate Memory-Agent-Pipeline ordnete unterschiedliche Reisen falsch zu; nicht wieder einführen. |
| 03.11.2026, Vorhaben | Idee wurde `proposed`, Entscheidung aktualisierte denselben Thread auf `active` mit nächstem Schritt; neue Unterhaltung fand ihn wieder. Unabhängiges Motorradthema änderte nur die passende Erinnerung. |
| 03.11.2026, Zeit | „15. März“ → 15.03.2027 plus zwei Wochen; „Mitte August nächstes Jahr“ → 10.–20.08.2027, approximate und Originaltext; relative Verschiebung Juni→September 2027. Keine erfundene harte Deadline. |
| 03.11.2026, Konsistenz | `gpt-5-mini` suchte bei storeübergreifenden Änderungen gelegentlich nur Threads oder nur Erinnerungen. Prompt verlangt für Zukunftsthemen beide Suchen; bei erneuter Flakiness stärkeres Modell/höheres Reasoning evaluieren. |
| 03.11.2026, Auswertung | Deadline in 17 Tagen erzeugte konkrete Empfehlung; Werkstatttermin nur als Erinnerung wurde als Vorschlag ohne Thread sichtbar. Zweiter Lauf keine exakten Duplikate, auch nicht nach Dismiss. PATCH 400/404 geprüft. |
| 03.11.2026, UI MVP 0.1 | Chat/Heute/Vorhaben und gemeinsame Services, echte DB mit Bestätigungs-Roundtrip und Entwurfserhalt ohne API-Key getestet. Historische Berichte nannten 90 Tests beziehungsweise einen Lauf mit 64 bestanden/27 übersprungen; unterschiedliche Teststände, keine aktuelle Gesamtaussage. |
| 04.11.2026 | Audit und Vorbereitung von Dockerfile, Compose, Worker, Migrationen und Betriebsanleitungen. **Kein Deployment**. Frühere Aussagen „produktionsbereit“, „alle Services getestet“ oder „automatische Migration bei jedem DB-Start“ waren zu weitgehend. |
| 06.11.2026, Auth | Zunächst 112 Tests bestanden, 29 DB-Tests übersprungen; danach 80 Auth-/Storage-/Webtests mit Docker-PostgreSQL ohne Skip bestanden. Lokale Anmeldung vom Nutzer bestätigt, HTTP-Cookies und IPv4-DB-Adresse korrigiert. |
| 06.11.2026, Bereinigung | Ausgangsschema zusammengeführt, versionierter Updateweg, Startbedingungen und gemeinsame Konfiguration ergänzt, Dokumentation auf zwei Dateien vereinigt. Validierung dieses Schritts siehe Tests und Diagnose. |

Übernommene Dokumente und Zielabschnitte:

| Frühere Datei | Inhalt jetzt hier |
|---|---|
| `QUICK_START.md` | Lokaler Start, erster Docker-Start, Konfiguration, Diagnose. |
| `DEPLOYMENT.md` | Docker-Betrieb, Updates, Backup/Restore, Proxy, Monitoring, Grenzen. |
| `PROD_COMPONENTS.md` | Architektur, Servicegraph, Healthchecks, Logging, Konfiguration. |
| `AUDIT_PROD_READY.md` | Entwicklungsgeschichte, korrigierter Betriebsstand, offene Roadmap. |
| `IMPLEMENTATION_SUMMARY.md` | Komponenten, Kompatibilität, Historie, weiterhin ungeprüfte Deployment-Schritte. |
| `WEB_UI_DOCUMENTATION.md` | Bedienung, Gestaltung/Accessibility, Dateien, API, Tests und UI-Grenzen. |
| `AUTHENTICATION.md` | Passwort, Sitzungsschutz, API-Zugriff, Konfiguration und Integrationstests. |
| Bisherige technische Teile von `AGENTS.md` | Datenmodell, Agentenverhalten, Verifikation, Historie und Roadmap. |

Widersprüche wurden in der aktuellen Anleitung berichtigt; historische
Beobachtungen und offene Fragen bleiben gekennzeichnet erhalten. Frühere
Dateilängen, die grobe 800-MB-Image-Schätzung und 10–20-Minuten-Installations-
schätzungen waren keine Mess-/Qualitätsnachweise. Wiederholte Statuslisten sind
zusammengeführt. Die Originale der bereits versionierten Dateien bleiben über
Git-Historie (`git log -- DATEI`) nachvollziehbar.

Technische Referenzen: [Compose-Startreihenfolge](https://docs.docker.com/compose/how-tos/startup-order/),
[Compose up](https://docs.docker.com/reference/cli/docker/compose/up/),
[PostgreSQL Advisory Locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS),
[Python scrypt](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt).
