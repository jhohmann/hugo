# Hugo

Hugo ist ein proaktiver persönlicher Assistent für Zeitplanung, längerfristige Vorhaben und Erinnerungen. Ein zentraler Agent verbindet Informationen, verfolgt offene Themen und schlägt nächste Schritte vor.

Im Chat stehen zeitliche Fragen im Mittelpunkt: Termine, Fristen, Vorlauf und
das Zusammenspiel mit anderen Aktivitäten. Hugo soll normalerweise in 2–4 kurzen
Sätzen antworten und höchstens einen konkreten nächsten Schritt nennen.
Allgemeine Anleitungen und Checklisten gibt es auf ausdrücklichen Wunsch.
Bei Terminwahl und Machbarkeit prüft er auch andere offene Vorhaben und den
Kalender; fehlende Informationen bleiben erkennbar.

- **Sprache:** Deutsch
- **Zeitzone:** Europe/Berlin
- **Entwicklung:** Python lokal, PostgreSQL in Docker
- **Betrieb:** Webserver und Worker auf einer Docker Engine, beispielsweise in einem Proxmox-Gast
- **Zugriff:** Ein Nutzer mit Passwortanmeldung

[AGENTS.md](AGENTS.md) beschreibt die Produktziele und Arbeitsregeln für Entwicklungsagenten.

## Inhalt

- [Lokale Einrichtung](#lokale-einrichtung)
- [Projektstruktur](#projektstruktur)
- [Bedienung](#bedienung)
- [Anmeldung und Sitzungen](#anmeldung-und-sitzungen)
- [Konfiguration](#konfiguration)
- [Docker-Betrieb](#docker-betrieb)
- [Updates und Migrationen](#updates-und-migrationen)
- [Backup und Wiederherstellung](#backup-und-wiederherstellung)
- [Reverse-Proxy und HTTPS](#reverse-proxy-und-https)
- [Architektur und Datenmodell](#architektur-und-datenmodell)
- [API](#api)
- [Tests und Diagnose](#tests-und-diagnose)
- [Grenzen und Weiterentwicklung](#grenzen-und-weiterentwicklung)

## Lokale Einrichtung

### Voraussetzungen

- Python 3.12 oder neuer
- Docker mit Compose v2
- Git
- OpenAI-API-Schlüssel oder optional eine freigeschaltete ChatGPT-Abo-Anmeldung (siehe OAuth-Einrichtung)

Die virtuelle Umgebung und die Datei `.env` liegen im Projektordner. Zugangsdaten gehören weder in Git noch in Docker-Images.

### Windows: Einrichtung

Im Projektordner ausführen:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d db
cd backend
..\.venv\Scripts\python.exe -m app.passwords
```

Die Passwortabfrage erzeugt eine Zeile `HUGO_PASSWORD_HASH=scrypt-v1:...`. Diese in `.env` eintragen.

Folgende Werte konfigurieren:

| Variable | Wert |
|---|---|
| `OPENAI_API_KEY` | Eigener API-Schlüssel |
| `HUGO_PASSWORD_HASH` | Erzeugter Passwort-Hash |
| `HUGO_COOKIE_SECURE` | `false` für lokales HTTP |
| `DATABASE_URL` | `postgresql://hugo:hugo_dev@127.0.0.1:5432/hugo` |

### Windows: Start

Im Projektordner ausführen:

```powershell
docker compose up -d db
cd backend
..\.venv\Scripts\python.exe -m app.dev
```

Die Oberfläche ist unter [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui) erreichbar. **Strg+C** beendet den Server.

`app.dev` lädt die Projekt-`.env`, führt ausstehende Migrationen aus und startet Uvicorn mit automatischem Neuladen des Anwendungscodes. Bei einem Migrationsfehler startet der Server nicht.

| Option | Funktion |
|---|---|
| `--port 8001` | Anderen Port verwenden |
| `--no-reload` | Automatisches Neuladen deaktivieren |
| `--env-file PFAD` | Andere Umgebungsdatei laden |

Änderungen an `.env` benötigen einen vollständigen Prozessneustart. Bereits gesetzte Prozessvariablen haben Vorrang vor der Datei.

### Linux und macOS

Im Projektordner ausführen:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
test -f .env || cp .env.example .env
docker compose up -d db
cd backend
../.venv/bin/python -m app.passwords
```

API-Schlüssel, Passwort-Hash und lokale Konfiguration in `.env` eintragen. Anschließend im Ordner `backend` starten:

```bash
../.venv/bin/python -m app.dev
```

### Worker

Der Worker läuft als separater Prozess. In einem zweiten Terminal im Ordner `backend` starten:

```powershell
..\.venv\Scripts\python.exe -m app.worker
```

Unter Linux und macOS lautet der Python-Pfad `../.venv/bin/python`.

- Der Worker lädt die Projekt-`.env`.
- Standardzeit: täglich **08:00 Uhr Europe/Berlin**, mit automatischer Sommer-/Winterzeit.
- Ohne Worker steht die manuelle Auswertung unter **Heute → Jetzt auswerten** zur Verfügung.
- Auswertungen verwenden die OpenAI-API und können Kosten verursachen.

### Einzelne Einstiegspunkte

Mit aktivierter virtueller Umgebung im Ordner `backend`:

```bash
# Nur Migrationen ausführen
python -m app.migrate

# Webserver ohne vorgeschaltete Migration starten
python -m uvicorn app.main:app --env-file ../.env --host 127.0.0.1 --port 8000 --reload
```

## Projektstruktur

```text
backend/
  app/
    agent/              Zentraler Agent und proaktive Auswertung
    calendar/           Google-Zugriff und freizugebende Aktionen
    storage/            PostgreSQL-Zugriff und Embeddings
    tools/              Zeitrechnung und Agentenwerkzeuge
    web/                UI-Routen, Templates und statische Dateien
  migrations/           Versionierte SQL-Migrationen
  requirements.txt      Laufzeitabhängigkeiten
  requirements-dev.txt  Laufzeitabhängigkeiten und Testwerkzeuge
tests/                  Automatisierte Tests
scripts/                Updates und manuelle Diagnose
pyproject.toml          Testkonfiguration
compose.yaml            Lokale Entwicklungsdatenbank
compose.prod.yaml       Docker-Stack mit Datenbank, Migration, Web, Worker und Caddy
Caddyfile               Reverse-Proxy-Konfiguration (Domain aus HUGO_DOMAIN)
Dockerfile              Gemeinsames Anwendungsimage
```

### Lokale Dateien

Diese Dateien und Verzeichnisse werden nicht versioniert:

| Pfad | Inhalt |
|---|---|
| `.env`, `.env.prod` | Zugangsdaten und lokale Konfiguration |
| `.venv/` | Installierte Python-Abhängigkeiten |
| `.pytest_cache/`, `pytest-cache-files-*/` | Testcaches |
| `__pycache__/` | Generierter Python-Bytecode |
| `*.log`, `logs/` | Laufzeitprotokolle |
| `backups/` | Datenbanksicherungen |
| `credentials.json`, `token.json` | Zugangsdaten für das manuelle Google-Diagnosewerkzeug |

Der Docker-Build übernimmt Anwendungscode, Migrationen und Laufzeitabhängigkeiten.

## Bedienung

Die Oberfläche unter `/ui` führt nach der Anmeldung zur Ansicht **Heute**. Inhaltliche Änderungen an Erinnerungen und Vorhaben erfolgen über den Chat.

Das Reglersymbol rechts oben öffnet die [Einstellungen](#einstellungen-in-der-oberfläche)
unter `/ui/settings` für Verbindungen, KI und tägliche Auswertungen.

### Chat

`/ui/chat` · `/ui/chat/{id}`

- Neue Unterhaltung beginnen oder vorhandene fortsetzen.
- Vollständigen Nachrichtenverlauf anzeigen.
- Die 50 jüngsten Unterhaltungen anhand ihrer ersten Nutzernachricht auswählen.
- Vorhaben über ihre sichtbare Kennung referenzieren, beispielsweise
  „Was fehlt noch bei V-42?“. **Vorhaben referenzieren** fügt die Kennung an der
  Cursorposition ein; ohne JavaScript wird die Auswahl beim Senden vorangestellt.
  Die Auswahl zeigt bis zu 500 Vorhaben; bekannte Kennungen können immer direkt
  eingegeben werden. Mehrere Kennungen in einer Nachricht sind möglich (höchstens zehn).
- Die Chatliste zeigt zugehörige Vorhaben als kompakte blaue Kennungen; über dem
  Gespräch führen Kennung und Titel direkt zur Vorhabenseite.
- Entwurf bei einem Agentenfehler erhalten.
- Mit **Enter** senden, mit **Shift+Enter** einen Zeilenumbruch einfügen.
- Der Nachrichtenverlauf scrollt innerhalb der verfügbaren Bildschirmhöhe;
  das Eingabefeld steht darunter und überlagert keine Nachrichten. Mit JavaScript
  passt sich die Chatfläche über `visualViewport` auch an die mobile Tastatur an
  ([Browser-Verhalten](https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport)).
  Beim Öffnen erscheint das Chatende; wer hochscrollt, behält seine Leseposition
  auch bei Größenänderungen. Kein automatischer Eingabefokus beim Seitenwechsel.
  Antworten erscheinen vollständig nach dem Neuladen, nicht als Textstream.

### Heute

`/ui/heute`

- Offene Vorschläge mit Begründung, Priorität P1–P5, Datum und Vorhabenbezug.
- Vorschläge bestätigen, zurückstellen oder verwerfen.
- Beim Zurückstellen unter **Wieder anzeigen am** ein zukünftiges Datum wählen.
- Zurückgestellte Vorschläge in einem einklappbaren Bereich.
- Letzten Auswertungslauf anzeigen und über **Jetzt auswerten** eine Auswertung starten.

Vorschläge entstehen durch manuelle oder geplante Auswertungen. Beim Anzeigen werden sie als zugestellt markiert.

### Vorhaben

`/ui/threads` · `/ui/threads/{id}`

- Bereiche **Arbeit** und **Privat** als Kennzeichnung und Filter.
- Ein Vorhaben kann beiden Bereichen oder keinem zugeordnet sein. **Alle Bereiche** zeigt auch unzugeordnete Vorhaben.
- Gruppierung nach Aktiv, Wartet und Idee; Erledigt und Archiviert sind einklappbar.
- Übersicht über nächsten Schritt, Priorität, Ereigniszeitraum und Fristen.
- Detailansicht mit Beschreibung, ursprünglicher Zeitangabe und zugehörigen Vorschlägen.
- Sichtbare Kennung **V-ID** in Liste und Detailkopf; **Mit Hugo besprechen** öffnet
  einen neuen Chat mit vorausgefüllter Referenz.
- **Gespräche zu diesem Vorhaben** zeigt verknüpfte Unterhaltungen aufklappbar,
  jeweils mit den letzten zwölf Nachrichten und einem Link zum vollständigen
  Chat zum Weiterschreiben. Fünf Gespräche je Seite, weitere über Seitennavigation.
  Eine Unterhaltung kann mehrere Vorhaben behandeln; der eingeblendete Verlauf
  enthält dann auch andere Themen.
- Wiedervorlage und **Wartet auf** für offene Rückmeldungen oder andere Voraussetzungen.

Im Chat lässt sich beispielsweise „Warte auf das Angebot von Müller; nächste Woche
wieder aufgreifen“ festhalten. Bei „Das Angebot ist da“ kann Hugo den Wartekontext
entfernen und den nächsten Schritt aktualisieren.

### Kalender

`/ui/kalender`

- Google-Konto verbinden oder trennen.
- Vorgeschlagene Kalenderaktionen, Konflikte und vergangene Aktionen anzeigen.
- Schreibaktionen ausdrücklich freigeben.

Die Bestätigung eines allgemeinen Vorschlags ersetzt keine Kalenderfreigabe. Kalenderaktionen haben einen eigenen Bestätigungsweg.

### Darstellung

Die Oberfläche verwendet serverseitige Jinja2-Templates und lokale CSS-/JavaScript-Dateien.

- Einspaltige Darstellung bis 760 px; Chat-Sidebar auf größeren Bildschirmen.
- Hell-/Dunkelmodus entsprechend der Systemeinstellung.
- Buttons, Menüpunkte und Formularfelder verwenden wieder den gemeinsamen
  Eckenradius von 10 Pixeln.
- Semantische Elemente, ARIA-Beschriftungen und Statusmeldungen für Tastatur und Screenreader.
- Hervorhebung hoher Prioritäten ab P4 und überfälliger Daten.
- Formulare funktionieren ohne JavaScript; Ladeanzeigen, Bestätigungsdialoge und Enter-zum-Senden benötigen JavaScript.

Listen sind begrenzt; die Gespräche auf Vorhabenseiten haben eine Seitennavigation.
Einklappbare Bereiche laden ihre Inhalte nicht separat nach.

## Anmeldung und Sitzungen

### Passwort

Hugo verwendet ein gemeinsames Passwort ohne Benutzernamen.

- Länge: 12 bis 1024 Zeichen.
- Konfiguration als gesalzener scrypt-Hash über `python -m app.passwords`.
- Ohne gültigen `HUGO_PASSWORD_HASH` bleibt die Anwendung gesperrt: HTTP 503.
- Höchstens zehn Anmeldeversuche pro Minute insgesamt, über alle IPs und Prozesse hinweg.
- Bei Überschreitung: HTTP 429 mit `Retry-After: 60`.

### Sitzungsdauer

| Anmeldung | Gültigkeit |
|---|---|
| Ohne „Angemeldet bleiben“ | Browser-Sitzungscookie, serverseitig höchstens 12 Stunden |
| Mit „Angemeldet bleiben“ | 30 Tage ab Anmeldung, auch über Neustarts hinweg |

Browser mit Sitzungswiederherstellung können Sitzungscookies erhalten. Es gibt keine gleitende Verlängerung.

Abmelden widerruft die aktuelle Sitzung. Ein neuer Passwort-Hash mit Neustart aller Webprozesse macht vorhandene Sitzungen ungültig.

### Zugriffsschutz

Das Cookie `hugo_session` enthält ein zufälliges Token. PostgreSQL speichert dessen SHA-256-Hash. Abgelaufene Sitzungen werden bei erfolgreicher Anmeldung bereinigt.

- Cookie-Eigenschaften: HttpOnly, SameSite=Lax und standardmäßig Secure.
- Für HTTPS: `HUGO_COOKIE_SECURE=true`.
- Für lokales HTTP: `HUGO_COOKIE_SECURE=false`.
- Geschützt: Oberfläche, JSON-API, API-Dokumentation und Kalenderaktionen.
- Öffentlich: Anmeldung, statische Dateien und `/health`.
- Geschützte Antworten verwenden `Cache-Control: no-store`.

### API-Anmeldung

1. `POST /ui/login` mit den Formfeldern `password` und optional `remember=true` senden.
2. Das zurückgegebene Cookie für weitere Anfragen übernehmen.
3. Für POST, PATCH, PUT und DELETE einen passenden `Origin` oder `Referer` mitsenden.

Skripte ohne Origin-/Referer-Header setzen `X-Hugo-Request: 1`, auch beim Login. Ein fremder Origin wird trotz dieses Headers abgewiesen.

Swagger unter `/docs` verwendet die Sitzung der Browser-Anmeldung.

## Konfiguration

### Einstellungen in der Oberfläche

Über das Reglersymbol rechts oben oder `/ui/settings` sind Verbindungen und
Anwendungseinstellungen zentral erreichbar, auch auf dem Smartphone:

- Google Kalender: gespeicherte Anmeldung, Verbindung herstellen/verwalten und
  ein ausdrücklich ausgelöster Zugriffstest. Ein Seitenaufruf allein kontaktiert
  Google nicht. Mail ist als zukünftige Verbindung vorgemerkt, ohne Mail-Zugriff.
- KI: Hugo-Version, konfiguriertes Modell, gespeicherte ChatGPT-Anmeldung,
  Vorhandensein des API-Schlüssels, bekannte Kontingentpause sowie Modell,
  Zeitpunkt und Tokens des letzten erfolgreichen Aufrufs über Abo oder API.
  Zugangsdaten werden nicht ausgegeben. Gespeicherte Anmeldung und letzter
  Erfolg sind kein aktueller Erreichbarkeitsnachweis; ein Restkontingent ist
  derzeit nicht abrufbar. Die Seite verlinkt zur Kontingentanzeige in ChatGPT.
- Änderbar: KI-Zugang und Hauptmodell, kostenpflichtige API-Reserve mit eigenem
  Modell und Wartezeit, Webrecherche samt Aktionslimit, Gesprächsbudget und
  tägliche Auswertungszeit (Europe/Berlin). Verfügbare Modellnamen hängen vom Zugang ab.
- Die letzte Auswertung wird mit Zeitpunkt, Auslöser und Ergebnis angezeigt;
  ein Worker-Live-Status wird mangels Heartbeat nicht behauptet.

Migration `008_app_settings.sql` ergänzt eine gemeinsame, nicht geheime
Einstellungszeile mit Revision und Änderungszeit. Zunächst gelten weiterhin
die Umgebungswerte. Nach dem Speichern haben die Werte der Seite Vorrang für
Web und Worker; „Servervorgaben wiederherstellen“ entfernt diese Überschreibung.
Veraltete Formulare erhalten HTTP 409, statt neuere Änderungen zu überschreiben.
Änderungen werden mit Revision protokolliert. Modellaufrufe und Werkzeugschleifen
verwenden einen konsistenten Einstellungsstand bis zu ihrem Abschluss.

Neue Aufrufe übernehmen Änderungen ohne Serverneustart. Ein laufender Worker
liest die Auswertungszeit alle 60 Sekunden und plant nur bei Änderung neu;
eine bereits vergangene neue Uhrzeit löst keine nachträgliche Auswertung aus.
Der Worker muss separat gestartet sein. Nach Installation dieser Codeänderung
muss ein bereits laufender Worker einmal neu gestartet werden.
Passwort, Schlüssel, Google-OAuth-Client, Datenbank-, Cookie-, Logging- und
Serveroptionen bleiben in der Umgebungskonfiguration und benötigen bei Änderungen
einen Neustart. Die Seite ist durch dieselbe Anmeldung und Origin-Prüfung wie
die übrige Anwendung geschützt.

### Datenbank

| Variable | Standard / Bedeutung |
|---|---|
| `DATABASE_URL` | Vollständiger Verbindungsstring; hat Vorrang vor einzelnen DB-Feldern |
| `DB_HOST` | Lokal `127.0.0.1`, im Docker-Stack `db` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `hugo` |
| `DB_USER` | `hugo` |
| `DB_PASSWORD` | Lokal `hugo_dev`; im Docker-Stack eigenes Passwort erforderlich |

Im Docker-Stack werden einzelne DB-Felder verwendet. Damit benötigen Sonderzeichen im Passwort kein URL-Encoding.

Die lokale `compose.yaml` startet nur PostgreSQL und bindet Port 5432 an `127.0.0.1`. Eine Änderung der Env-Datei ändert nicht das Passwort einer bereits initialisierten PostgreSQL-Rolle.

### Anwendung

| Variable | Standard / Bedeutung |
|---|---|
| `OPENAI_API_KEY` | API-Schlüssel für Modellaufrufe mit `HUGO_MODEL_PROVIDER=api` |
| `HUGO_MODEL_PROVIDER` | `api`; alternativ `chatgpt` für das eigene ChatGPT-Abo per OAuth |
| `HUGO_MODEL` | Bei API-Nutzung standardmäßig `gpt-5.6-terra`; bei OAuth ausdrücklich einen verfügbaren Modell-Slug wählen |
| `HUGO_API_FALLBACK_ENABLED` | `false`; bei `true` nach einer ausdrücklich gemeldeten Abo-Kontingentgrenze kostenpflichtig über den API-Schlüssel fortsetzen |
| `HUGO_API_FALLBACK_MODEL` | `gpt-5.6-terra`; Modell für diese API-Reserve, unabhängig vom Abo-Modell |
| `HUGO_CHATGPT_RETRY_SECONDS` | `1800`; frühester erneuter Abo-Versuch nach erkanntem Limit, zulässig 60–86400; kein zugesagter Kontingent-Reset |
| `HUGO_WEB_SEARCH_ENABLED` | `true`; native Webrecherche in Chat und Auswertungen, mit `false` abschalten |
| `HUGO_WEB_SEARCH_MAX_CALLS` | `3`; höchstens 1–10 native Webaktionen je Agentenlauf |
| `HUGO_CHAT_HISTORY_TOKENS` | `12000`; weiches Budget für den Gesprächsverlauf in geschätzten Tokens, zulässig 2000–60000 |
| `HUGO_PASSWORD_HASH` | Mit `app.passwords` erzeugter Hash |
| `HUGO_COOKIE_SECURE` | `true`; für lokales HTTP `false` |
| `LOG_LEVEL` | `INFO`; Uvicorn hat zusätzlich eigene CLI-Logoptionen |
| `SCHEDULER_HOUR` | `8`, Stunde in Europe/Berlin von 0 bis 23 |
| `SCHEDULER_MINUTE` | `0`, Minute von 0 bis 59 |

Seit 11.11.2026 beziehen sich die Scheduler-Werte auf Berliner Ortszeit statt UTC.
Bestehende Umgebungswerte und gespeicherte Einstellungen bei Updates entsprechend
prüfen; lokal wurden beide auf 08:00 Uhr gestellt. Docker übergibt dieselben
Vorgaben an Web und Worker, damit Einstellungsseite und Ausführung übereinstimmen.

`gpt-5-mini` wird am **11.12.2026** abgeschaltet. Der API-Standard und die
API-Reserve verwenden deshalb den [offiziell empfohlenen Ersatz
`gpt-5.6-terra`](https://developers.openai.com/api/docs/deprecations).
Das Modell unterstützt Responses, Function Calling, Websuche und niedrigen
Reasoning-Aufwand. Für Hugos mehrstufige Planung ist die Balance aus Leistung
und Kosten der Auswahlgrund; eine allgemeine Qualitätsverbesserung ist damit
noch nicht nachgewiesen. Standardpreise pro Million Tokens: **2 USD Eingabe /
12 USD Ausgabe**, gegenüber zuvor 0,25 / 2 USD; die Reserve ist somit teurer
([Modellinformationen](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[bisheriges Modell](https://developers.openai.com/api/docs/models/gpt-5-mini)).
Das lokal konfigurierte Abo-Hauptmodell bleibt `gpt-6.1-sol`.

### ChatGPT-Abo per OAuth (optional)

Der alternative Modellzugriff verwendet die offiziell dokumentierte
[ChatGPT-Plan-Nutzung per OAuth](https://developers.openai.com/siwc/token-sharing-open-source).
Hugo registriert sich als eigener lokaler Client; eine vorhandene Codex-Anmeldung
wird nicht ausgelesen. Ein zusätzlicher Codex-Prozess ist dafür nicht erforderlich.
Chat, Kontextverdichtung und geplante Auswertungen verwenden denselben gewählten
Zugang. Datenbank, Agentenwerkzeuge und Kalenderfreigaben bleiben bei Hugo.

Die Verfügbarkeit hängt vom Konto, Workspace und der Freischaltung durch OpenAI
ab. Es entsteht kein zusätzliches Kontingent; Nutzung und App-Limits werden in
den [ChatGPT-Nutzungseinstellungen](https://chatgpt.com/settings/usage) verwaltet.
Modellkatalog und erfolgreiche Anmeldung allein belegen keinen funktionierenden
Modellaufruf. Der Zugang befindet sich laut Dokumentation im Preview.

Einrichtung unter Windows aus dem Projektverzeichnis, nach Installation der
aktuellen `backend/requirements.txt`:

```powershell
.venv/Scripts/python.exe scripts/chatgpt_login.py login
.venv/Scripts/python.exe scripts/chatgpt_login.py models
```

`login` migriert zuerst die Datenbank und zeigt dann einen Link für den lokalen
Browser. Dort persönlich anmelden und Hugo die Nutzung des Abos erlauben. Der
einmalige Callback läuft ausschließlich auf `127.0.0.1`; die Anmeldung verfällt
nach zehn Minuten. Danach in `.env` `HUGO_MODEL_PROVIDER=chatgpt` und
`HUGO_MODEL=<Slug aus dem Modellkatalog>` eintragen. Anschließend genau einen
kleinen echten Modellaufruf prüfen und Web/Worker neu starten:

```powershell
.venv/Scripts/python.exe scripts/chatgpt_login.py check
```

`check` nutzt ausdrücklich OAuth und sendet nur eine kurze synthetische Frage;
es verwendet keine persönlichen Vorhaben und keine Werkzeuge. Der bestehende
API-Schlüssel wird im OAuth-Modus nur für die ausdrücklich aktivierte API-Reserve genutzt.
Rückkehr zur API: `HUGO_MODEL_PROVIDER=api`, gegebenenfalls `HUGO_MODEL=gpt-5.6-terra`
setzen und Prozesse neu starten.

- `status` zeigt Verbindung, Abrechnungsweg, Kontingentpause und den letzten
  abgeschlossenen Modellaufruf, ohne Zugangstokens auszugeben.
- Mit `HUGO_API_FALLBACK_ENABLED=true` übernimmt bei
  `subscription_sharing_usage_limit_exceeded` die kostenpflichtige API über
  `OPENAI_API_KEY`. Der fehlgeschlagene Modellaufruf wird einmal mit dem
  Reservemodell fortgesetzt. Teilantworten werden verworfen; bereits
  ausgeführte lokale Werkzeugaufrufe und ihre Ergebnisse bleiben als Kontext
  erhalten. Fremde verschlüsselte Reasoning-Daten werden beim Wechsel entfernt.
  Normale 429-Rate-Limits, Netzwerk-, Berechtigungs- und Anmeldefehler lösen
  keinen Wechsel der Abrechnung aus. Ein fehlender API-Schlüssel oder Fehler
  der API-Reserve wird sichtbar gemeldet, ohne weitere Ausweichschleife.
- Während der Kontingentpause verwenden Chat, Verdichtung und Worker die
  aktivierte API-Reserve. Nach standardmäßig 30 Minuten versucht genau eine
  neue Anfrage das Abo erneut; parallele Anfragen bleiben vorerst bei der API.
  Bei Erfolg kehrt Hugo zum Abo zurück. Ohne eingehende Anfrage erfolgt kein
  zusätzlicher Modellaufruf. `resume` erlaubt einen sofortigen neuen Versuch.
  Ohne aktivierte Reserve erhält der Nutzer während der Pause eine Fehlermeldung.
- Im Chat zeigt eine kompakte aufklappbare Anzeige den Zugangsstatus, die
  kostenpflichtige Reserve, den Zeitpunkt des nächsten Abo-Versuchs und
  Eingabe-/Ausgabetokens des letzten abgeschlossenen Modellaufrufs an.
  Diese Tokens sind keine Restkontingent- oder Kostenberechnung. Für den
  verwendeten direkten OAuth-Zugang ist keine verlässliche öffentliche Abfrage
  der verbleibenden Abo-Menge dokumentiert; die Anzeige verlinkt deshalb
  [ChatGPT → Nutzung](https://chatgpt.com/settings/usage). Ein gemeldetes Limit
  kann nur Hugo betreffen, und der lokale Wiederholungsabstand ist keine
  Prognose für die Rücksetzung des Limits.
- `logout` versucht die Sitzung bei OpenAI zu widerrufen und entfernt lokale
  Tokens. Schlägt der Widerruf fehl, wird dies angezeigt. Die registrierte
  Client-ID und Host-ID bleiben für die erneute Anmeldung erhalten. Dieser
  Ausbau unterstützt ein ChatGPT-Konto, keinen Kontowechsel in der UI.
- OAuth-State, PKCE und signierte ID-Tokens mit Nonce, Issuer, Audience und
  Ablaufzeit werden geprüft. Migration `007_model_oauth.sql` speichert die
  Anmeldung in einer separaten Tabelle; sie wird nie als Modellkontext gelesen.
  Wie Google-Tokens sind diese Zugangsdaten Bestandteil der geschützten
  Datenbank und ihrer Backups. Web und Worker erneuern rotierende Tokens unter
  derselben PostgreSQL-Sperre. Temporäre Fehler löschen die Verbindung nicht.

Für Docker verwenden Web und Worker dieselbe Datenbankanmeldung und die neuen
Umgebungsvariablen aus `.env.prod`. Für eine erstmalige Anmeldung auf einer
eigenen VM kann das lokale Anmeldeskript über einen geschützten SSH-Tunnel zur
VM-Datenbank arbeiten (`--env-file` mit deren Verbindungsdaten); der Browser und
Callback bleiben lokal. Die VM verwaltet danach die Token-Erneuerung. Eine neue
Installation benötigt eine eigene Host-ID; bestehende angemeldete Installationen
nicht gleichzeitig als Klone betreiben. Proxmox- und unbeaufsichtigter
OAuth-Dauerbetrieb sind noch nicht verifiziert.

Die [Preview-Grenzen](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
verlangen Streaming und `store=false`. Hugo wartet vor Werkzeugausführung auf
eine vollständig abgeschlossene Antwort und übergibt bei Folgerunden den Kontext
einschließlich verschlüsselter Reasoning-Inhalte. Feste `max_output_tokens` und
`max_tool_calls` sind bei diesem Zugang nicht verfügbar: Werkzeugrunden bleiben
begrenzt, die maximale Anzahl nativer Webaktionen wird aber erst nach einer
Antwort geprüft. Eine Überschreitung lässt den Lauf fehlschlagen, kann bereits
verbrauchten Modell-/Webbedarf jedoch nicht verhindern. Websuche und Modellwahl
hängen zusätzlich von den Fähigkeiten des jeweiligen Kontos ab.

### Google Calendar

| Variable | Bedeutung |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth-Client-ID |
| `GOOGLE_CLIENT_SECRET` | OAuth-Client-Secret |
| `GOOGLE_REDIRECT_URI` | Exakt die bei Google registrierte Callback-URL |

Lokale Callback-URL:

```text
http://127.0.0.1:8000/ui/kalender/auth/callback
```

Für den externen Betrieb die entsprechende HTTPS-Adresse verwenden. Ohne OAuth-Konfiguration bleibt der Kalender unverbunden.

### Docker und Proxy

| Variable | Standard / Bedeutung |
|---|---|
| `WEB_PORT` | `127.0.0.1:8000`; Format `[BIND_ADRESSE:]PORT` |
| `HUGO_IMAGE` | `hugo:local`; gemeinsames Image für Web, Worker und Migration |
| `HUGO_DOMAIN` | Öffentlicher Name für den Caddy-Proxy, erforderlich |
| `HUGO_TLS_INTERNAL` | `true` für lokale Namen ohne öffentliche Auflösung (Caddy-interne CA) |
| `HTTP_PORT` / `HTTPS_PORT` | Veröffentlichte Proxy-Ports, Standard `80`/`443` |
| `FORWARDED_ALLOW_IPS` | `172.16.0.0/12` (Docker-Netz des Caddy-Proxys) |

Vorlagen: [`.env.example`](.env.example) für lokale Entwicklung und [`.env.prod.template`](.env.prod.template) für Docker.

## Docker-Betrieb

### Voraussetzungen

- Linux-Gast mit Docker Engine und Compose v2
- Git und Zugriff auf den Host
- Ausgehender Internetzugang für OpenAI, Google und Modell-Downloads
- Speicherplatz für Datenbank, Modelle, Images und Backups

Docker-Installation: [offizielle Debian-Anleitung](https://docs.docker.com/engine/install/debian/).

### Einrichtung

```bash
git clone https://github.com/jhohmann/hugo.git /opt/hugo
cd /opt/hugo
cp .env.prod.template .env.prod
chmod 600 .env.prod
docker build -t hugo:local .
docker run --rm -it --entrypoint python hugo:local -m app.passwords
```

In `.env.prod` eintragen:

- Eigenes DB-Passwort, beispielsweise erzeugt mit `openssl rand -hex 32`
- OpenAI-API-Schlüssel oder eingerichtete ChatGPT-Abo-Anmeldung
- Erzeugten Passwort-Hash
- `HUGO_DOMAIN` für den Caddy-Proxy (siehe [Reverse-Proxy und HTTPS](#reverse-proxy-und-https))
- Bei Bedarf Google-OAuth-Konfiguration

Bei späteren Updates ergänzt [`scripts/merge-env.sh`](scripts/merge-env.sh) neue Schlüssel aus der Vorlage in der bestehenden `.env.prod`, ohne vorhandene Werte zu ändern. Das Update-Skript ruft es automatisch auf.

### Start

```bash
docker compose --env-file .env.prod -f compose.prod.yaml up -d --build
docker compose --env-file .env.prod -f compose.prod.yaml ps -a
docker compose --env-file .env.prod -f compose.prod.yaml logs migrate web worker
curl --fail http://127.0.0.1:8000/health
```

`compose.prod.yaml` ist eigenständig und wird nicht mit `compose.yaml` kombiniert.

### Services

| Service | Aufgabe | Startbedingung |
|---|---|---|
| `db` | PostgreSQL 17 mit pgvector | Keine |
| `migrate` | Einmaliger Schemalauf | Datenbank gesund |
| `web` | FastAPI/Uvicorn | Migration erfolgreich |
| `worker` | Tägliche Auswertung | Migration erfolgreich |
| `caddy` | Reverse-Proxy mit TLS | Web gesund |

Der Migrationscontainer beendet sich bei Erfolg mit Exitcode 0. Die Datenbank hat keinen veröffentlichten Port; der Webserver bindet standardmäßig an Loopback. Caddy veröffentlicht die Ports 80 und 443 und leitet an `web:8000` weiter.

### Speicherung und Netzwerk

- `hugo_postgres_data` enthält die Datenbank.
- `model_cache` hält die heruntergeladenen Modelle.
- `caddy_data` und `caddy_config` enthalten Zertifikate und Laufzeitdaten des Proxys.
- Web, Worker und Caddy verwenden ein internes DB-Netz und ein zusätzliches Netz für ausgehende Verbindungen.
- Das Image verwendet Python 3.12, CPU-PyTorch und den Nutzer `hugo` ohne Root-Rechte.
- Eine GPU ist nicht erforderlich.

Compose-Volumes gehören zum jeweiligen Projektnamen. Ein anderer Projektname verwendet andere Volumes.

### Healthchecks und Logs

| Service | Prüfung | Logrotation |
|---|---|---|
| Datenbank | Alle 5 Sekunden | 10 MB × 3 |
| Web | Alle 30 Sekunden, 90 Sekunden Startfrist | 50 MB × 5 |
| Worker | Kein HTTP-Healthcheck | 30 MB × 3 |
| Caddy | Admin-API alle 30 Sekunden | 10 MB × 3 |

`/health` prüft den Webprozess, nicht die Datenbank oder Anmeldung. `restart: unless-stopped` startet beendete Prozesse neu; ein Status `unhealthy` allein löst keinen Neustart aus.

```bash
docker compose --env-file .env.prod -f compose.prod.yaml logs -f web
docker compose --env-file .env.prod -f compose.prod.yaml logs --since 24h worker
docker compose --env-file .env.prod -f compose.prod.yaml stop web worker
```

`restart` übernimmt weder neue Images noch geänderte Umgebungsvariablen. Dafür `up -d` verwenden. `down` ohne `--volumes` erhält benannte Volumes.

## Updates und Migrationen

Ein Update umfasst Code, Abhängigkeiten, Datenbankschema und Prozessneustart. Vor Schemaänderungen die Datenbank sichern und Web sowie Worker stoppen.

### Lokale Entwicklung

Im Projektordner, nach dem Stoppen der Anwendung und dem Backup:

```powershell
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'Git-Update fehlgeschlagen' }

.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation fehlgeschlagen' }

docker compose up -d db
if ($LASTEXITCODE -ne 0) { throw 'Datenbankstart fehlgeschlagen' }

cd backend
..\.venv\Scripts\python.exe -m app.dev
```

Einen separat verwendeten Worker anschließend neu starten. Unter Linux und macOS den Python-Pfad `.venv/bin/python` verwenden und bei Fehlern abbrechen.

### Docker-Host

```bash
bash scripts/update.sh
```

Das [Update-Skript](scripts/update.sh) benötigt eine saubere getrackte Arbeitskopie und führt folgende Schritte aus:

1. Code mit `git pull --ff-only` aktualisieren.
2. Gemeinsames Image bauen.
3. Datenbankbereitschaft prüfen.
4. Web und Worker stoppen.
5. Datenbank nach `backups/` sichern.
6. Migrationen ausführen.
7. Web und Worker mit dem neuen Image starten.

Bei Build-Fehlern läuft die Anwendung weiter. Nach einem Migrationsfehler bleiben Web und Worker gestoppt. Ein automatischer Daten-Rollback erfolgt nicht.

### Migrationsdateien

[`backend/migrations/001_initial.sql`](backend/migrations/001_initial.sql) definiert das Ausgangsschema. Weitere Migrationen heißen `002_<name>.sql`, `003_<name>.sql` usw.

- Angewendete Dateien nicht ändern, umbenennen oder löschen.
- Neue Dateien in aufsteigender Reihenfolge ergänzen.
- Keine eigenen `COMMIT`-/`ROLLBACK`-Kommandos verwenden.
- Nichttransaktionale Operationen wie `CREATE INDEX CONCURRENTLY` benötigen einen gesonderten Ablauf.

### Ausführung

Erstinstallation und Updates verwenden `app.migrate`.

- `schema_version` speichert Nummer, Dateiname, SHA-256-Prüfsumme und Zeitpunkt.
- Eine PostgreSQL-Advisory-Lock verhindert gleichzeitige Migrationsläufe.
- Jede Datei und ihr Versionsvermerk werden gemeinsam in einer Transaktion ausgeführt.
- Bei einem Fehler wird diese Transaktion zurückgerollt; abgeschlossene Migrationen bleiben bestehen.
- Fehlende oder veränderte Dateien sowie eine zum Code neuere Datenbank blockieren den Lauf.
- LF und CRLF ergeben dieselbe Prüfsumme.

Eine vollständige, unversionierte Entwicklungsdatenbank kann ohne Löschen der Inhalte übernommen werden. Fehlende benötigte Spalten verhindern die Übernahme.

## Backup und Wiederherstellung

Ein PostgreSQL-Dump enthält die Anwendungsdaten einschließlich Google- und ChatGPT-OAuth-Tokens, Sitzungshashes und Migrationshistorie. Sicherungen geschützt ablegen und regelmäßig eine Wiederherstellung in einer getrennten Datenbank prüfen.

Lokale Entwicklung und Docker-Betrieb haben getrennte Datenbestände. Ein Datentransfer erfolgt über Dump und Restore.

### Backup unter Linux

Im Projektordner:

```bash
mkdir -p backups
chmod 700 backups
umask 077
docker compose --env-file .env.prod -f compose.prod.yaml exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/hugo.dump
```

Je Sicherung einen eigenen Dateinamen verwenden. Das Update-Skript fügt einen Zeitstempel hinzu.

### Backup unter Windows

Den binären Dump im Container erzeugen und anschließend kopieren:

```powershell
docker compose exec -T db pg_dump -U hugo -d hugo -Fc -f /tmp/hugo-backup.dump
if ($LASTEXITCODE -ne 0) { throw 'Backup fehlgeschlagen' }

$dbContainer = docker compose ps -q db
New-Item -ItemType Directory -Force backups | Out-Null
docker cp "${dbContainer}:/tmp/hugo-backup.dump" backups/hugo-backup.dump
```

Binäre Dumps nicht durch Textumleitungen älterer PowerShell-Versionen leiten.

### Aufbewahrung

- Regelmäßige Backups zusätzlich zu Updates einplanen.
- Sicherungen außerhalb des Docker-Hosts aufbewahren.
- Speicherplatz und Sicherungserfolg überwachen.
- Aufbewahrungsfrist festlegen und nur das eigene Backup-Verzeichnis bereinigen.

### Wiederherstellung

Zunächst eine neue Datenbank verwenden:

```bash
docker compose --env-file .env.prod -f compose.prod.yaml exec -T db sh -c \
  'createdb -U "$POSTGRES_USER" hugo_restore'

docker compose --env-file .env.prod -f compose.prod.yaml exec -T db sh -c \
  'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d hugo_restore' < backups/hugo.dump
```

Für die lokale Entwicklung `docker compose` ohne Produktionsdatei verwenden. Unter Windows den Dump mit `docker cp` in den Container kopieren und `pg_restore` dort mit Dateipfad aufrufen.

Vor dem Umschalten:

1. Code-Stand, Schema-Version und Daten prüfen.
2. Web und Worker stoppen.
3. Verbindung auf die wiederhergestellte Datenbank umstellen.
4. Die ursprüngliche Datenbank bis zur erfolgreichen Prüfung behalten.

### Rollback

Bei inkompatiblen Schemata benötigt ein Rollback den passenden Code-/Image-Stand und den Datenstand vor dem Update.

Zwischenzeitliche Änderungen vor einer Wiederherstellung sichern und gegebenenfalls separat übernehmen.

## Reverse-Proxy und HTTPS

Für externen Zugriff HTTPS verwenden. Der Docker-Stack enthält Caddy als Reverse-Proxy; die Konfiguration liegt in der [Caddyfile](Caddyfile) und leitet an `web:8000` weiter. Caddy setzt die benötigten `Host`- und `X-Forwarded-*`-Header automatisch.

### TLS einrichten

1. `HUGO_DOMAIN` in `.env.prod` auf den öffentlichen Namen setzen.
2. Öffentlich auflösbarer Name: DNS auf den Docker-Host zeigen lassen, Ports 80 und 443 erreichbar machen. Caddy bezieht und erneuert das Zertifikat automatisch.
3. Nur lokaler Name (z. B. `hugo.fritz.box`): `HUGO_TLS_INTERNAL=true` setzen. Caddy stellt ein Zertifikat der eigenen CA aus. Gegen Browser-Warnungen die Root-CA einmalig auf den Clients installieren:

   ```bash
   docker compose --env-file .env.prod -f compose.prod.yaml \
     cp caddy:/data/caddy/pki/authorities/local/root.crt caddy-root.crt
   ```

4. `HUGO_COOKIE_SECURE=true` setzen (Standard).
5. Google-Callback-URL auf die HTTPS-Adresse umstellen.

### Proxy-Vertrauen und Ports

- `FORWARDED_ALLOW_IPS` muss das Docker-Netz des Caddy-Proxys umfassen; Standard `172.16.0.0/12`.
- Den Backend-Port 8000 nur für den Proxy erreichbar machen (`WEB_PORT=127.0.0.1:8000`).
- PostgreSQL-Port 5432 nicht extern veröffentlichen.
- Falsche Host-/Protokollangaben können bei Formularen HTTP 403 auslösen.
- Mit `HUGO_COOKIE_SECURE=true` ist eine Anmeldung über unverschlüsseltes HTTP (z. B. direkt über die IP) nicht mehr möglich; der Browser speichert das Secure-Cookie dort nicht.

Hugo verwendet keine WebSockets.

## Architektur und Datenmodell

### Komponenten

| Komponente | Technik |
|---|---|
| Backend | Python, FastAPI |
| Modellzugriff | OpenAI Responses API; API-Schlüssel oder ChatGPT-Abo per OAuth, Modell konfigurierbar |
| Datenbank | PostgreSQL 17, pgvector, psycopg |
| Oberfläche | Jinja2, lokale CSS-/JavaScript-Dateien |
| Scheduling | APScheduler |
| Embeddings | `intfloat/multilingual-e5-small`, 384 Dimensionen |

Embeddings sind normalisiert und verwenden `query:`-/`passage:`-Präfixe. Die Suche nutzt HNSW-Indizes mit Cosinus-Abstand.

Das Modell wird bei Bedarf geladen und pro Prozess gehalten. Der Docker-Modellcache vermeidet wiederholte Downloads; Web und Worker benötigen jeweils eigenen Arbeitsspeicher.

### Zentrale Module

Die Pfade beziehen sich auf `backend/app/`.

| Modul | Verantwortung |
|---|---|
| `main.py` | JSON-Endpunkte und Einbindung der Oberfläche |
| `chat_service.py` | Gemeinsame Chatlogik für API und UI |
| `agent/assistant.py` | Systemprompt und begrenzte Tool-Calling-Schleife |
| `agent/model_client.py`, `agent/chatgpt_auth.py` | Wählbarer Modellzugang, Streaming, OAuth-Prüfung und Token-Erneuerung |
| `agent/model_usage.py` | Kontingentpause, koordinierter Wiederholungsversuch und öffentliche Statusdaten ohne Zugangstokens |
| `storage/model_oauth.py` | Gemeinsame, serialisierte OAuth-Anmeldung für Web und Worker |
| `agent/chat_context.py` | Budgetabhängige Verdichtung älterer Gesprächsteile und vollständiger jüngster Verlauf |
| `storage/conversation_context.py` | Gespeicherte Zusammenfassungen mit Nachrichtenmarke und Schutz vor konkurrierenden Updates |
| `storage/thread_chats.py`, `tools/thread_references.py` | Explizite Vorhabenreferenzen, Nachrichtenverknüpfungen und Gesprächsansichten |
| `agent/web_research.py` | Webrecherche-Konfiguration, Rechercheanweisungen und dauerhafte Quellenlinks |
| `agent/evaluation.py` | Proaktive Auswertung über dieselbe Schleife |
| `calendar/` | OAuth, Google-REST-API, Konfliktprüfung und freigegebene Ausführung |
| `storage/` | Persistenz und semantische Suche |
| `tools/dates.py` | Zeitkontext und Datumsarithmetik |
| `web/routes.py` | UI-Routen |
| `web/formatting.py` | Deutsche Datums- und Statusdarstellung |
| `auth.py`, `passwords.py` | Zugriffsschutz, Anmeldung und Passwort-Hash |
| `config.py`, `dev.py` | Konfiguration und lokaler Start |
| `migrate.py` | Versionierte Schemaänderungen |
| `worker.py` | Geplante Auswertungen |

UI und JSON-API verwenden dieselben Fach- und Speicherfunktionen.

Der zentrale Modellaufruf verwendet `text.verbosity=low` für kurze Ausgaben
([OpenAI Docs](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_new_params_and_tools)).
Der Chatprompt konkretisiert den zeitlichen Fokus, knappe Antworten und den
Abgleich mit anderen Vorhaben; geplante Auswertungen verlangen ebenfalls kurze,
zeitbezogene Vorschläge. Das Ausgabetokenbudget bleibt für Reasoning und
Werkzeugaufrufe erhalten. Antworten werden nicht nachträglich abgeschnitten;
ausdrücklich gewünschte ausführliche Antworten bleiben möglich.

### Internetrecherche

Hugo kann öffentliche aktuelle Informationen über die native
[`web_search` der OpenAI Responses API](https://developers.openai.com/api/docs/guides/tools-web-search)
recherchieren. Der bestehende zentrale Agent und API-Schlüssel werden verwendet;
es gibt keinen zusätzlichen Rechercheagenten, Crawler oder Suchanbieter-Schlüssel.
Beispiel: „Wann findet die nächste Red Bull Romaniacs statt?“

- Das Modell entscheidet über Suchbegriffe und Folgeaktionen. Die Anweisungen
  verlangen bei aktuellen Informationen eine Recherche, bevorzugt Primärquellen,
  und unterscheiden Veranstaltungsjahr, Austragungszeitraum und Anmeldefrist.
  Fehlende oder widersprüchliche Angaben dürfen nicht als gesicherter Termin gelten.
- Websuche ist auch in proaktiven Auswertungen verfügbar, aber nur bei einer
  konkreten offenen Frage eines relevanten Vorhabens vorgesehen. Eine Recherche
  bedeutet keine Teilnahme oder Buchung. Die Kalenderfreigabe bleibt erforderlich.
- Die API erhält je Modellrunde das verbleibende `max_tool_calls`-Budget.
  Zurückgelieferte Webaktionen werden über die Runden hinweg gezählt; nach
  Verbrauch entfällt das Webwerkzeug. Die bestehende Grenze von acht Modellrunden
  bleibt bestehen. Chatantworten haben ein Ausgabelimit von 4.000 Tokens inklusive
  Reasoning, proaktive Auswertungen weiterhin 3.000. Das ist kein Euro-Kostenlimit.
- Websuche und das zusätzliche Modell-/Suchkontextvolumen verursachen API-Kosten.
  Abschaltung und Budget sind in `.env` beziehungsweise `.env.prod` konfigurierbar.
  Für Änderungen Webserver/Worker neu starten beziehungsweise Container neu erstellen.
- URL-Quellenannotationen werden direkt am belegten Antworttext zu Markdown-Links.
  Sie bleiben im bestehenden Nachrichten-TEXT und in der JSON-Antwort erhalten;
  es ist keine Migration erforderlich. Chat, Vorschläge und Vorhabenbeschreibungen
  stellen Quellenlinks anklickbar dar; sonstiger Text und HTML bleiben escaped.
  Bei übernommenen Recherchefakten soll das Modell Quelle, Recherchetag und
  Unsicherheit im bestehenden Inhalt erhalten.
- Webseiten sind als unvertrauenswürdige Daten gekennzeichnet. Suchanfragen sollen
  nur benötigte öffentliche Begriffe enthalten, keine privaten Kontextdaten.
  Diese Auswahl ist modellgesteuert, kein technischer Inhaltsfilter. Wie zuvor
  erhält der Modellanbieter den für den Agentenlauf relevanten Gesprächskontext.
- Jeder Lauf kann ausschließlich seine freigegebenen lokalen Funktionswerkzeuge
  ausführen. Native Webaufrufe werden nicht als lokale Funktionen dispatcht.
  Webstatus, Aktionstyp und Tokenverbrauch werden protokolliert, ohne Suchtexte,
  Antwortinhalte oder Werkzeugargumente ins normale Werkzeuglog zu schreiben.
- Providerfehler, fehlgeschlagene Webaktionen und unvollständige Modellantworten
  schlagen als Agentenfehler durch. Im Chat bleibt der Entwurf erhalten; eine
  proaktive Auswertung wird als fehlgeschlagen erfasst. Es gibt keinen stillen
  Rückfall auf eine angeblich recherchierte Antwort aus Trainingswissen.

Die Suche kann unvollständig oder veraltet sein; Quellen sind prüfbare Belege,
keine Garantie für richtige Interpretation. Webseiten hinter Anmeldung oder
Zugriffssperren sind nicht zuverlässig recherchierbar. Wiederholte Recherchen und
die Relevanz autonomer Hinweise müssen im laufenden Betrieb beobachtet werden.

### Unterhaltungen und Erinnerungen

| Tabelle | Inhalt |
|---|---|
| `conversations` | Unterhaltungen |
| `messages` | Nachrichten und Rollen |
| `conversation_summaries` | Ersetzbare Gesprächszusammenfassung, letzte enthaltene Nachrichten-ID und Änderungszeit |
| `memories` | Inhalt, Kategorie, Gültigkeit, Quelle, Zeitstempel und Embedding |

Erinnerungen haben den Status `proposed`, `confirmed` oder `outdated`. Exakte Duplikate werden unterdrückt. `update_memory` verändert nur Erinnerungen mit Status `proposed`.

Kurze Chats senden ihren gesamten Verlauf. Oberhalb von `HUGO_CHAT_HISTORY_TOKENS`
verdichtet ein separater, werkzeugloser Aufruf desselben Modells ältere Nachrichten.
Die Zusammenfassung wird pro Unterhaltung gespeichert und später zusammen mit
den noch nicht verdichteten Nachrichten wiederverwendet. Bei erneutem Überschreiten
werden nur bisher unverdichtete Nachrichten zusammen mit dem bestehenden
Zwischenstand verarbeitet. Das ist eine Kontextaufbereitung, kein weiterer
Agent mit eigenen Aktionen. Die manuelle Verwaltung des Gesprächskontexts folgt
dem [Responses-API-Prinzip](https://developers.openai.com/api/docs/guides/conversation-state).

Mindestens die letzten sechs Nachrichten sowie ungefähr ein Drittel des Budgets
bleiben vollständig erhalten; die Grenze wird zum Beginn einer Nutzernachricht
zurückgeschoben. Ziele, Korrekturen, Entscheidungen, Unsicherheiten und offene
Abhängigkeiten sollen erhalten bleiben. Quellnachrichten enthalten für die
Verdichtung ihren Erfassungszeitpunkt, damit ältere relative Datumsangaben nicht
auf heute verschoben werden. Die Zusammenfassung wird als historischer Kontext
mit Nutzerrolle eingefügt, niemals als Systemanweisung. Aktuelle Nutzeraussagen
und über Werkzeuge geprüfte Planungsdaten bleiben maßgeblich.

Das Budget betrifft nur die Historie, nicht Systemprompt, Werkzeuge oder neu
abgerufene Ergebnisse. Die Schätzung verwendet UTF-8-Bytes/3 plus acht Tokens je
Nachricht, keinen modellspezifischen Tokenizer. Sie ist keine harte Kontextgrenze.
Pro Anfrage erfolgen höchstens vier Zusammenfassungsaufrufe mit begrenzten
Nachrichtenpaketen, jeweils maximal 4000 Ausgabetokens und 60 Sekunden ohne
automatische Wiederholung. Ein einzelner sehr großer Beitrag wird nicht zerteilt.
Zusammenfassungen sind auf höchstens 6000 Zeichen begrenzt, bei kleinem Budget
entsprechend weniger. Leere, unvollständige, zu lange oder nicht verkleinernde
Ergebnisse werden verworfen. Bei Modell-/Speicherfehlern oder konkurrierenden
Updates bleibt der vorherige Zwischenstand mit allen restlichen Nachrichten erhalten.
Dadurch kann das weiche Budget überschritten werden; sehr große Chats können
weiterhin die Modellgrenze erreichen. Fehlerarten und Tokenverbrauch werden ohne
Gesprächsinhalte protokolliert.

Migration `006_conversation_summaries.sql` ergänzt ausschließlich abgeleiteten
Kontext. Originalnachrichten, vollständige Anzeige und Nachrichten-API bleiben
erhalten. Zusammenfassungen sind auf die jeweilige Unterhaltung begrenzt und
ersetzen keine langfristigen Erinnerungen oder Vorhaben. Parallele Anfragen
können zusätzliche Zusammenfassungsaufrufe verursachen; ein veralteter
Zwischenstand kann einen neueren nicht überschreiben. Der gesamte Chatablauf
ist dadurch noch nicht gegen gleichzeitige Nutzernachrichten serialisiert.

### Vorhaben

`threads` speichert Titel, Beschreibung, Priorität, nächsten Schritt und Zeitfelder.

| Status | Bedeutung |
|---|---|
| `proposed` | Idee oder unverbindliche Überlegung |
| `active` | Konkretes Vorhaben |
| `waiting` | Wartend |
| `completed` | Erledigt |
| `archived` | Archiviert |

`thread_memories` und `thread_messages` verknüpfen Vorhaben mit Wissen und Quellnachrichten.

Die sichtbare Kennung `V-42` entspricht der vorhandenen numerischen Vorhaben-ID 42;
es gibt keinen zweiten Nummernkreis. Der Chatdienst prüft ausdrücklich geschriebene
Kennungen vor dem Speichern gegen den aktuellen Bestand und reicht die gefundenen
Vorhaben als Kontextdaten an das Modell weiter, auch bei verdichteter Chathistorie.
Eine Referenz verändert das Vorhaben nicht. Ungültige oder unbekannte Kennungen
führen zu HTTP 400 mit erhaltenem Entwurf in der Oberfläche. Das gilt auch für
Referenzen im Nachrichtenfeld der JSON-API; deren Anfrageformat bleibt unverändert.

Explizite Referenzen verknüpfen die Nutzernachricht über `thread_messages`; nach
einer Antwort werden deren Verknüpfungen übernommen. Dabei werden auch vom Modell
beim Anlegen/Aktualisieren eines Vorhabens erzeugte Bezüge berücksichtigt.
Die Ansichten leiten Gesprächszugehörigkeit aus diesen Nachrichtenverknüpfungen
ab. Bestehende Verknüpfungen werden sichtbar; alte Gespräche ohne solche Bezüge
werden nicht rückwirkend semantisch zugeordnet. Eine spätere explizite Referenz
kann eine bestehende Unterhaltung zuordnen. Die bestehenden Tabellen reichen aus;
für diese Funktion ist keine neue Migration nötig.

`thread_tags` ordnet einem Vorhaben die Bereiche `arbeit` und `privat` zu.
Die Zuordnung erfolgt über den Chat, beispielsweise „Ordne die Fortbildung Arbeit zu“
oder „Entferne die Bereichszuordnung“. Hugo verwendet eindeutigen Kontext und
berücksichtigt Nutzerkorrekturen. Bei unklarem Kontext bleibt die Zuordnung offen.

Die Thread-Werkzeuge geben `tags` als Liste zurück. Beim Erstellen und Aktualisieren
setzt eine Liste die vollständige Zuordnung; `[]` entfernt alle Tags, `null` lässt
die Zuordnung unverändert. Suchen und Auflisten unterstützen den optionalen Filter
`tag`. Bereiche dienen der Organisation, nicht der Zugriffskontrolle.

Die Agentenwerkzeuge `search_threads`, `list_threads`, `get_thread`, `create_thread` und `update_thread` verwenden IDs aus vorherigen Such- oder Leseaufrufen. Updates verändern nur ausdrücklich mitgegebene Felder.

### Zeitleisten-Vorschau

`/ui/zeitleiste` ist die Vorbereitung für eine grafische Vorhabenansicht.
Die lokale Datenvorschau unter `/ui/zeitleiste?demo=1` verwendet ausschließlich
gekennzeichnete, fiktive Beispieldaten im Speicher. Zum Aktivieren auf dem
Test-PC `HUGO_TIMELINE_DEMO=true` setzen und den Entwicklungsserver neu starten.
Standardmäßig ist der Demo-Modus deaktiviert; die Anmeldung bleibt erforderlich.
Die Vorschau und ihre Navigation verändern weder Vorschläge noch Vorhaben.
Die grafische Darstellung und die Anbindung realer Daten stehen noch aus.

### Ereignisprotokoll

`thread_events` erfasst Erstellung und relevante Änderungen durch die
Thread-Speicherfunktionen. Ein Speichervorgang erzeugt einen Eintrag mit den
tatsächlich geänderten Feldern, ihren vorherigen und neuen Werten sowie dem
Erfassungszeitpunkt. Zustand und Ereignis werden gemeinsam gespeichert oder
bei einem Fehler gemeinsam zurückgerollt. Unveränderte Werte, Embeddings und
Lesezugriffe erzeugen keine Ereignisse.

Eine verknüpfte Quellnachricht kennzeichnet den Gesprächskontext; ohne sie ist
die Herkunft interne Pflege. Das belegt keine ausdrückliche Nutzerbestätigung.
Beim Abschluss automatisch geleerte Wartefelder werden zusätzlich markiert.
Das Protokoll beginnt mit Migration `005_thread_events.sql`; frühere Änderungen
werden nicht aus dem aktuellen Zustand rekonstruiert. Direkte SQL-Änderungen
außerhalb der Speicherfunktionen werden nicht protokolliert. Beim Löschen eines
Threads werden auch dessen Ereignisse entfernt.

Das lesende Agentenwerkzeug `list_thread_events` steht im Chat und in der
proaktiven Auswertung zur Verfügung. Hugo kann damit bei Bedarf frühere
Änderungen oder Wartezeiten eines bekannten Vorhabens nachvollziehen.
Die Ergebnisse enthalten Herkunft, Vorher-/Nachher-Werte und Hinweise auf
automatische Bereinigungen. Fehlende Einträge belegen keine Untätigkeit.

Pro Abruf werden höchstens 100 Ereignisse in Erfassungsreihenfolge geliefert.
`has_more` und `next_after_id` ermöglichen das Nachladen mit denselben Filtern.
`since` (inklusive) und `until` (exklusive) begrenzen den Erfassungszeitpunkt;
beide erwarten ISO-Zeitstempel mit Zeitzone. Ein unbekannter Thread wird von
einem vorhandenen Thread ohne passende Ereignisse unterschieden. Abfragen
verändern keine Daten. Die grafische Zeitleiste ist noch nicht angebunden.

### Zeitplanung

| Feld | Bedeutung |
|---|---|
| `event_start`, `event_end` | Ereignistag oder inklusiver Zeitraum |
| `time_precision` | `exact` oder `approximate` |
| `time_text` | Ursprüngliche Zeitangabe |
| `deadline` | Vom Nutzer genannte harte Frist |
| `act_by` | Hugos empfohlener Handlungstermin |
| `review_on` | Nächster interner Prüftermin, unabhängig von einer Deadline |
| `waiting_for` | Auf wen oder was gewartet wird |
| `blocked_reason` | Hindernis, das den Fortschritt verhindert |
| `preparation_weeks` | Benötigte Vorbereitungszeit in Wochen |

Ein Ereignisende benötigt einen Anfang und darf nicht davor liegen. Offene Vorhaben werden nach dem frühesten Wert aus Prüftermin, Handlungstermin, Ereignisbeginn und Deadline geordnet.

Jeder Agentenaufruf erhält Datum, Uhrzeit und deutschen Wochentag in Europe/Berlin. `compute_date` unterstützt Tage, Wochen, Monate und Jahre einschließlich Monatsenden und Schaltjahren.

Chat und Hintergrundauswertung erhalten dieselben Anweisungen zur eigenständigen
Kritikalitätsbewertung: vom Zieltermin rückwärts anhand von Prioritäten,
Verbindlichkeit, Verzögerungsfolgen, Abhängigkeiten und tatsächlich nutzbaren
Handlungsfenstern. Dazu sollen andere Vorhaben und Kalender im relevanten
Vorbereitungszeitraum geprüft werden. Fehlende Kalenderdaten oder unbekannte
Dauern gelten als Unsicherheit, nicht als freie Kapazität. Die Einschätzung
erfolgt durch das Modell, ohne feste Warnabstände oder Regeln für einzelne Lebensbereiche.

Hugo soll interne Erinnerungen und Vorhaben ohne Speicherfreigabe pflegen und
selbst entscheiden, wann ein Hinweis nützlich ist. Im Chat kann es begründete
Handlungstermine (`act_by`) und nächste Schritte eigenständig aktualisieren.
`act_by` ist eine revidierbare Empfehlung; frühere Hinweise bleiben möglich.
`review_on` dient ausdrücklich gewünschtem Zurückstellen und soll nicht als
automatisch gesetzte Warnschwelle verwendet werden. Rückfragen betreffen nur
entscheidungsrelevante fehlende Sachangaben. Externe Änderungen bleiben freigabepflichtig.

Fehlende Bezugspunkte bei relativen Zeitangaben führen zu einer Rückfrage. Datetimes ohne Zeitzone werden als UTC interpretiert.

`update_thread` kann über `clear_fields` die Felder `review_on`, `waiting_for` und
`blocked_reason` gezielt entfernen. `null` lässt Werte unverändert. Beim Abschluss
oder Archivieren werden diese Felder geleert und offene oder zurückgestellte
Vorschläge des Vorhabens verworfen.
Das ausdrückliche Entfernen eines Wartekontexts oder Blockers verwirft ebenfalls
die bisherigen offenen Hinweise zu diesem Vorhaben. Neue nächste Schritte können
anschließend eigene Vorschläge erhalten.

### Wiedervorlage und Zurückstellen

- Ein zukünftiges `review_on` pausiert neue Hinweise zu diesem Vorhaben. Bereits
  offene Hinweise werden bis zu diesem Datum zurückgestellt.
- `deferred_until` legt fest, an welchem Tag ein Vorschlag wieder offen wird.
- Maßgeblich ist der Kalendertag in **Europe/Berlin**. Es gibt keine stündlichen Erinnerungen.
- Fällige Vorschläge werden bei einer Auswertung oder beim Abrufen der Vorschläge
  einmalig wieder geöffnet und als noch nicht zugestellt markiert.
- Ein späterer Prüftermin des Vorhabens verhindert eine frühere Wiedervorlage.
- Solange ein Vorschlag zurückgestellt ist, werden keine neuen Vorschläge mit
  demselben Vorhabenbezug angelegt. Das gilt auch bei anderer Formulierung.
- Vorschläge ohne Wiedervorlagedatum bleiben unbefristet zurückgestellt. In der
  Heute-Ansicht kann ein Datum ergänzt werden.

Der Chat verwendet `list_suggestions` zum Finden eines Vorschlags und
`defer_suggestion` zum datierten Zurückstellen. Ein erreichter Prüftermin ist ein
Anlass zur Bewertung; das Modell entscheidet, ob ein konkreter Hinweis sinnvoll ist.

### Proaktive Auswertung

Die Auswertung berücksichtigt offene Vorhaben, jüngste Erinnerungen und offene oder zurückgestellte Vorschläge. Sie verwendet lesende Werkzeuge und `create_suggestion` über den zentralen Agenten.

Der Startkontext enthält bis zu 50 offene Vorhaben einschließlich zurückgestellter
Vorhaben: Auch diese können den Spielraum anderer Pläne einschränken. Ihre
Hinweispause bleibt durch die Vorschlagsspeicherung geschützt. Weitere Angaben
kann das Modell über lesende Werkzeuge ermitteln; `compute_date` steht auch hier
zur Verfügung. Die Auswertung entscheidet bei jedem Lauf neu über Anlass,
Zeitpunkt und Priorität eines Vorschlags, auch ohne vorhandenes `act_by` oder
`preparation_weeks`. Sie verändert weiterhin keine Vorhaben oder Erinnerungen.

| Tabelle | Inhalt |
|---|---|
| `evaluation_runs` | Auslöser, Status, betrachtete Vorhaben, Vorschlagszahl, Fehler und Laufzeiten |
| `suggestions` | Text, Grund, Priorität 1–5, Datum sowie Vorhaben- und Laufbezug |

| Zustand | Werte |
|---|---|
| Auslöser | `manual`, `scheduled` |
| Auswertung | `running`, `completed`, `failed` |
| Zustellung | `pending`, `surfaced` |
| Bearbeitung | `open`, `confirmed`, `deferred`, `dismissed` |

Exakt normalisierte Vorschläge werden pro Vorhaben über Auswertungsläufe und Bearbeitungsstatus hinweg dedupliziert. Umformulierungen können erneut erscheinen.

### Kalender und Freigaben

Google Calendar verwaltet tatsächliche Termine. Hugos Vorhaben bilden die interne Planungsebene.

| Tabelle | Inhalt |
|---|---|
| `google_credentials` | OAuth-Zugang eines Google-Kontos |
| `google_oauth_states` | Einmalige OAuth-States |
| `calendar_actions` | Vorgeschlagene Aktionen, Payload, Snapshot und Ergebnis |
| `calendar_action_log` | Aktionshistorie einschließlich Löschungen |

Kalenderaktionen haben den Status `pending`, `confirmed`, `rejected`, `executed`, `failed` oder `conflict`.

- Erstellen, Ändern und Löschen benötigen eine ausdrückliche UI-/API-Freigabe.
- Konflikte verlangen eine erneute Bestätigung.
- Deterministische Event-IDs vermeiden doppelte Neuanlagen bei Wiederholung.
- Hugo-Termine erhalten `[H]` und einen Änderungsverlauf.
- Zeitzonen und exklusive Enddaten ganztägiger Google-Termine werden berücksichtigt.
- Access- und Refresh-Tokens bleiben in PostgreSQL und werden nicht an das Modell übergeben.

Das lesende Agentenwerkzeug `search_events` sucht im Chat und in proaktiven
Auswertungen nach bereits eingetragenen Terminen. Der Zeitraum wird bei jedem
Aufruf aus dem aktuellen Datum in **Europe/Berlin** bestimmt: vom 1. Januar des
laufenden Jahres bis zum 1. Januar des übernächsten Jahres (exklusiv), also
beispielsweise das gesamte Jahr 2026 und 2027. Vergangene Termine des laufenden
Jahres sind eingeschlossen; über die Jahresgrenze reichende Termine können
ebenfalls enthalten sein.

- `query` ist ein kurzer Suchbegriff (1–200 Zeichen). Die
  [Google-Freitextsuche](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
  durchsucht unter anderem Titel, Beschreibung, Ort und Teilnehmer. Sie ist
  keine semantische Suche; Hugo wählt Begriffe und mögliche Alternativen.
  Bei einer leeren Suche soll Hugo bis zu zwei sinnvolle Schreibvarianten oder
  charakteristische Einzelwörter selbstständig prüfen, bevor er nachfragt.
- `calendar_id=null` durchsucht alle Kalender der verbundenen Kalenderliste,
  einschließlich ausgeblendeter Kalender. Eine ID beschränkt die Suche.
  Kalender mit ausschließlich Frei-/Belegt-Rechten werden unter
  `unsearchable_calendars` ausgewiesen. Private Inhalte bleiben von den
  Google-Leserechten abhängig.
- Kalender- und Termin-IDs werden als einzelne URL-Pfadsegmente kodiert.
  Das ist insbesondere bei `#` in Feiertags- und Kalenderwochenkalendern nötig;
  andernfalls kann ein solcher Kalender die gesamte Suche mit HTTP 404 abbrechen.
- Alle Google-Ergebnisseiten werden nachgeladen. Serien werden in einzelne
  Vorkommen aufgelöst; abgesagte Termine werden ausgeschlossen. Die Treffer
  werden kalenderübergreifend chronologisch sortiert.
- `limit` (1–100, normalerweise 20) und `offset` (anfangs 0) begrenzen nur die
  Antwort an das Modell. `total_count`, `has_more` und `next_offset` ermöglichen
  das Nachladen mit denselben Suchparametern. `time_min`, `time_max` und
  `searched_calendars` dokumentieren den Suchbereich.
- Jeder Abruf sucht erneut live; es gibt keinen lokalen Terminindex oder
  festen Ergebnissnapshot. Änderungen zwischen Abrufen können die Reihenfolge
  verschieben. Bei einem API-Fehler wird keine Teilliste als erfolgreiche Suche
  zurückgegeben. Andere Zeiträume bleiben über `list_events` abrufbar; dessen
  bisherige Ergebnisbegrenzung wird durch das neue Werkzeug nicht verändert.

Beispiel im Chat: „Wann ist meine nächste Fortbildung?“ Die Suche benötigt
keine Schreibfreigabe und verändert keine Termine.

### Sitzungen und Schema

| Tabelle | Inhalt |
|---|---|
| `auth_sessions` | Sitzungshashes, Passwortversion und Ablauf |
| `auth_login_limit` | Gemeinsamer Anmeldezähler |
| `schema_version` | Migrationshistorie |
| `model_oauth` | ChatGPT-OAuth-Registrierung, Host-ID, Tokens und Kontingentpause (geheim, kein Modellkontext) |
| `app_settings` | Nicht geheime Anwendungseinstellungen mit Revision und Änderungszeit |

## API

Nach der Anmeldung stehen `/docs`, `/redoc` und `/openapi.json` zur Verfügung. Die serverseitigen UI-Routen sind nicht im OpenAPI-Schema enthalten.

### Anwendung und Wissen

| Methode | Route | Zweck |
|---|---|---|
| GET | `/` | Name, Version und Status |
| GET | `/health` | Öffentlicher Prozesscheck |
| POST | `/chat` | Nachricht und optionale `conversation_id` |
| GET | `/conversations` | Jüngste Unterhaltungen |
| GET | `/conversations/{id}/messages` | Nachrichten einer Unterhaltung |
| GET | `/memories` | Erinnerungen anzeigen |
| GET | `/threads` | Vorhaben; optionale Filter `status` und `tag=arbeit` oder `tag=privat` |

### Auswertung und Vorschläge

| Methode | Route | Zweck |
|---|---|---|
| POST | `/proactivity/evaluate` | Manuelle Auswertung |
| GET | `/proactivity/runs` | Auswertungsprotokoll |
| GET | `/suggestions` | Vorschläge mit `status`-/`delivery`-Filter |
| PATCH | `/suggestions/{id}` | Bestätigen, zurückstellen oder verwerfen |

Zurückgegebene ausstehende Vorschläge werden als `surfaced` markiert.

Datiertes Zurückstellen:

```json
{"status": "deferred", "deferred_until": "2027-03-15"}
```

Das Datum muss in der Zukunft liegen. Bei anderen Statuswerten ist
`deferred_until` nicht zulässig. Ohne Datum ist Zurückstellen unbefristet.

### Kalender

| Methode | Route | Zweck |
|---|---|---|
| GET | `/calendar/status` | Konfiguration und Verbindungsstatus |
| GET | `/calendar/actions` | Aktionen; optionaler `status`-Filter |
| POST | `/calendar/actions/{id}/confirm` | Freigabe und Ausführung; optional `force` |
| POST | `/calendar/actions/{id}/reject` | Aktion ablehnen |
| POST | `/calendar/disconnect` | Google-Verbindung trennen |

### UI- und OAuth-Routen

| Methode | Routen |
|---|---|
| POST | `/ui/login`, `/ui/logout`, `/ui/chat`, `/ui/evaluate` |
| POST | `/ui/suggestions/{id}`, `/ui/calendar-actions/{id}` |
| POST | `/ui/kalender/disconnect` |
| GET, POST | `/ui/settings` (anzeigen, speichern oder auf Servervorgaben zurücksetzen) |
| POST | `/ui/settings/calendar-check` (lesender Kalenderzugriffstest) |
| GET | `/ui/kalender/auth/start`, `/ui/kalender/auth/callback` |

### Fehler und Begrenzungen

| HTTP-Status | Bedeutung |
|---|---|
| 400 | Ungültiger Filter oder ungültige Aktion |
| 401 | Fehlende API-Sitzung |
| 403 | Ungültiger Anfrage-Ursprung |
| 404 | Objekt nicht gefunden |
| 409 | Kalenderkonflikt, bereits behandelte Aktion oder veraltetes Einstellungsformular |
| 429 | Anmeldelimit erreicht |
| 502 | Externer Servicefehler |
| 503 | Anmeldung nicht eingerichtet oder Dienst nicht verfügbar |

Die Oberfläche leitet bei fehlender Sitzung zur Anmeldung weiter.

Die meisten JSON-Listen begrenzen `limit` auf 1–500. Für vollständige Datensicherungen `pg_dump` verwenden.

## Tests und Diagnose

Prüfung vom 11.11.2026: Modellwechsel und täglicher Zeitplan

- `tests/test_worker.py`, `tests/test_settings.py`, `tests/test_model_oauth.py`,
  `tests/test_config.py`, `tests/test_chat_context.py` und `tests/test_web.py`:
  **105 bestanden, 2 optionale Browsertests übersprungen**. Die Worker-Tests
  prüfen 08:00 Uhr Berlin im Winter, Sommer und an beiden Zeitumstellungstagen.
- `scripts/check_model_fallback.py`: echter synthetischer Werkzeugaufruf über
  `gpt-6.1-sol` (82 Eingabe-/14 Ausgabetokens) und erfolgreiche Fortsetzung über
  `gpt-5.6-terra` (111/5 Tokens). Keine echte Kontingentgrenze ausgelöst.
- Lokale `.env` und gespeicherte Einstellungen sind aktualisiert. Kein separater
  Worker lief; der angebotene Hintergrundstart wurde abgelehnt. Ein tatsächlicher
  geplanter Lauf um 08:00 Uhr ist daher noch offen. Nächster Schritt: Worker
  starten und die nächste geplante Auswertung beobachten. Kein Deployment geprüft.

Prüfung des zeitlichen Antwortfokus: zwei gezielte Tool-Loop-Tests bestanden
(`tests/test_web_research.py`, Auswahl `web_and_function_results_continue` und
`disabled_search_and_evaluation`). Sie prüfen unter anderem `verbosity=low`
bei Chat-/Webwerkzeugen und der geplanten Bewertung bei erhaltenem Tokenbudget.
Zwei anschließende echte Modellproben mit fiktiven Werkzeugdaten
(`scripts/check_chat_focus.py`) lieferten nach Promptnachschärfung Antworten mit
26 bzw. 27 Wörtern: Kalenderkonflikt plus anschließende Projektabgabe nach
`list_threads`/`list_events`, sowie eine gezielte Monatsfrage bei offenem Zeitraum.
Der erste Probelauf war bereits kurz, hatte aber andere Vorhaben nicht abgefragt
und interne Begriffe ausgegeben. Diese Punkte waren im zweiten Lauf korrigiert.
Keine echten Nutzer-, Kalender- oder Gesprächsdaten gelesen oder verändert;
die zwei Beispiele belegen keine allgemeine Erfolgsquote, keinen Worker-Lauf
und keine bereits erfolgte Übernahme auf Proxmox.

Chat-Layout am 08.11.2026: zwei gezielte Edge-Browserprüfungen bestanden
(`tests/test_chat_browser.py`, opt-in mit `HUGO_BROWSER_TESTS=1`; Playwright und
lokales Edge erforderlich). Geprüft wurden lange Verläufe, Leseposition beim
Verkleinern, Chatende, Radien sowie ein separat verkleinertes/verschobenes
`visualViewport` als Tastatursimulation. Die Prüfung rendert die echten Vorlagen
mit Beispieldaten ohne Backend-, Datenbank- oder Modellzugriff. Screenshots liegen
lokal unter `logs/chat-*.png`. Eine echte Bildschirmtastatur unter iOS/Android ist
damit noch nicht verifiziert; nächster Praxisschritt ist eine Probe am Handy.

### Automatisierte Tests

Im Projektordner:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

`pyproject.toml` begrenzt die Tests auf `tests/` und setzt den Importpfad auf `backend`. Manuelle Diagnosewerkzeuge werden nicht ausgeführt.

| Testbereich | Voraussetzungen |
|---|---|
| Web, Agentenwerkzeuge, Datumslogik, Auswertung | Gemockte Dienste, kein OpenAI-Zugriff |
| Auth-Speicherung | PostgreSQL; temporäre Schemas |
| Migrationen | PostgreSQL; Berechtigung zum Erstellen von Testdatenbanken |
| Vorhaben und Vorschläge | Konfigurierte Testdatenbank; gegebenenfalls Embedding-Download |
| Docker | Gebautes Image und ausdrücklich aktivierter Smoke-Test |

Datenbanktests werden ohne erreichbares PostgreSQL übersprungen. Tests nicht gegen eine produktive Datenbank ausführen.

Verifikation der Einstellungsseite am 11.11.2026:

- Migration `008_app_settings.sql` lokal angewendet. Echte temporäre
  PostgreSQL-Datenbanken prüfen Speicherung, Revisionen, Zurücksetzen,
  Migrationserhalt und parallele Migrationsläufe; keine bestehenden Daten gelöscht.
- Gezielte Tests prüfen Formularvalidierung, Anmeldung und Origin-Schutz,
  keine Ausgabe von Schlüsseln, Konfliktschutz gegen veraltete Formulare,
  Laufzeitübernahme, konsistente Agenteneinstellungen und Änderung der
  Worker-Uhrzeit ohne doppelte Auswertungsjobs. Bestehende OAuth-, Chatkontext-,
  Web-, Agentenwerkzeug-, Recherche- und Auswertungstests ebenfalls geprüft.
  Der explizite OAuth-Prüfbefehl bleibt auch bei gespeichertem API-Zugang beim Abo.
- Vier Edge-Browserprüfungen bestanden: Einstellungsseite und bestehender Chat,
  jeweils Desktop/Smartphone, einschließlich Speichern, echter Weiterleitung,
  Neuladen, Tastaturbereich im Chat und Einstellungsseite bis 320 Pixel Breite.
  Screenshots liegen unversioniert unter `logs/settings-*.png`; Hell- und
  Dunkeldarstellung gesichtet. Eine anfangs zu breite mobile Navigation mit
  Hinweiszähler ist korrigiert.
- Keine echten Modellaufrufe oder Kalenderabfragen für diese Prüfung.
  Verbindungsantworten waren simuliert. Ein dauerhafter Hintergrundbetrieb und
  reale Verbindungsprüfungen bleiben separat zu beobachten; nächster Schritt
  ist die Nutzung der Seite im Alltag und die Beobachtung geplanter Auswertungen.

Verifikation der API-Reserve und Kontingentanzeige am 11.11.2026:

- Die vorhandene OAuth-Anmeldung wurde bestätigt und der Modellkatalog wirklich
  abgerufen. Lokal ist `chatgpt` mit `gpt-6.1-sol` aktiviert; auf ausdrücklichen
  Nutzerwunsch übernimmt bei einer Kontingentgrenze die API mit `gpt-5-mini`.
  Schlüssel und Tokens wurden nicht ausgegeben. Keine Schemaänderung nötig.
- 134 gezielte Testfälle bestanden (OAuth, Web, Chatkontext, Agentenwerkzeuge,
  Webrecherche), davon zuletzt 31 OAuth-/Reserve-Tests nach korrigierter
  Testisolation. Abgedeckt sind Quotenfehler vor und während des Streams,
  Erhalt ausgeführter Werkzeugschritte, keine Abrechnungswechsel bei anderen
  Fehlern, fehlende Schlüssel, deaktivierte Reserve, koordinierter einzelner
  Wiederholungsversuch in echter temporärer PostgreSQL-Datenbank und Rückkehr
  zum Abo. Die Quotenfehler selbst werden simuliert.
- `scripts/check_model_fallback.py` hat mit zwei echten synthetischen Aufrufen
  die Übernahme eines Werkzeugergebnisses vom Abo in die API bestätigt:
  `gpt-6.1-sol` 82 Eingabe-/14 Ausgabetokens, `gpt-5-mini` 108 Eingabe-/71
  Ausgabetokens. Keine persönlichen Daten oder externen Aktionen. Ein zuvor
  vorübergehend fehlgeschlagener Tokenabruf war beim anschließenden
  Modellkatalogabruf wieder erfolgreich. Keine echte Kontingentgrenze erzeugt.
- Die Anzeige zeigt bekannte Zustände und den letzten erfolgreichen Aufruf,
  kein geschätztes Restguthaben. Nächster betrieblicher Schritt ist die
  Beobachtung eines tatsächlichen Kontingentwechsels im Alltag; tatsächliche
  Abo-Resetzeiten und der VM-Dauerbetrieb bleiben ungeprüft.
- Zwei Browserprüfungen mit lokalem Edge bestanden: Desktop und Smartphone,
  aufgeklappte Statusanzeige und verkleinerter Tastaturbereich. Die zusätzliche
  Anzeige wird bei sehr kleiner mobiler Höhe während der Texteingabe verborgen,
  damit das Eingabefeld erreichbar bleibt. Screenshots liegen unversioniert
  unter `logs/model-usage-*.png`. Compose-Konfiguration validiert; Hugo lokal
  über `app.dev` mit der neuen Konfiguration gestartet, `/health` liefert 200.

Historische Verifikation des optionalen ChatGPT-OAuth-Zugangs am 10.11.2026:

- 140 Testfälle in gezielten Läufen bestanden: OAuth, Migrationen, Chatkontext,
  Agentenwerkzeuge, Auswertung, Webrecherche und Weboberfläche. Nach Anpassung
  der Migrationsanzahl und Ergänzung der UI-Prüfung bestanden zuletzt alle
  67 OAuth-/Migrations-/UI-Tests. Keine übersprungenen Tests und keine echten
  Modellaufrufe. Geprüft sind signierte JWTs samt Nonce/Issuer/Audience/Ablauf,
  ungültige Callbacks, fehlende Abo-Freigabe, echte SDK-Streamverarbeitung,
  Werkzeugausgaben, Abbrüche, Kontingentpause und unveränderter API-Anfragepfad.
- Echte temporäre PostgreSQL-Datenbanken belegen Migrationserhalt und genau
  eine Token-Erneuerung bei konkurrierenden Zugriffen; der OAuth-Server ist
  dabei simuliert. Migration `007_model_oauth.sql` ist lokal angewendet.
- Hilfeskript und Verbindungsstatus lokal ausgeführt; noch kein ChatGPT-Konto
  verbunden. Compose-Konfiguration mit einem temporären Prüfwert für den
  erforderlichen Passwort-Hash validiert; kein Container neu gestartet.
- Nächster Schritt ist die persönliche Anmeldung, anschließende Modellwahl
  und ein kleiner echter Aufruf über `scripts/chatgpt_login.py check`. Reale
  OAuth-Freischaltung, Modell-/Websuche-Kompatibilität, Token-Erneuerung beim
  Anbieter und unbeaufsichtigter VM-Betrieb sind damit ausdrücklich noch
  nicht belegt. Der bisherige API-Modus bleibt aktiviert.

Verifikation der Vorhabenreferenzen am 09.11.2026:

- `tests/test_thread_references.py`, `tests/test_conversation_context.py`,
  `tests/test_web.py`, `tests/test_thread_tools.py` und `tests/test_follow_up.py`:
  **78 Tests bestanden**, keine übersprungen. Echte PostgreSQL-Prüfungen belegen
  die eindeutige Zuordnung gleichnamiger Vorhaben, aktuellen Kontext im
  Modellaufruf, Nachrichten-/Antwortverknüpfungen und Seitennavigation.
  Ungültige Referenzen, mehrere Bezüge, HTML-Escaping und Auswahl ohne
  JavaScript sind ebenfalls geprüft. Modellantworten waren simuliert.
- `tests/test_chat_browser.py`: **2 Browserprüfungen bestanden** mit lokalem Edge,
  Desktop und Smartphone einschließlich Tastaturverkleinerung, Kennungsauswahl
  ohne Duplikate und eingeblendeten Gesprächen. Screenshots liegen unversioniert
  unter `logs/chat-*.png` und `logs/thread-chat-*.png`.
- Keine Schemaänderung und kein Zugriff auf echte Kalender oder Modelle nötig.
  Nächster Schritt: Zuordnung und Lesbarkeit bei alltäglichen Gesprächen mit
  mehreren Vorhaben beobachten. Frühere Gespräche ohne gespeicherten Bezug
  bleiben zunächst unzugeordnet.

Verifikation der Gesprächsverdichtung am 09.11.2026:

- `tests/test_chat_context.py`, `tests/test_conversation_context.py`,
  `tests/test_migrations.py`, `tests/test_web.py` und `tests/test_config.py`:
  **63 Tests bestanden**, einschließlich Nachprüfung der auf sechs erhöhten
  Migrationsanzahl. Keine übersprungenen Tests. Abgedeckt sind Budgetauslösung,
  vollständiger jüngster Verlauf, Wiederverwendung und Fortschreibung,
  Fehlerfälle ohne Abschneiden, Trennung der Unterhaltungen, konkurrierende
  Zwischenstände und Migrationserhalt in temporären PostgreSQL-Datenbanken.
- Migration `006_conversation_summaries.sql` wurde lokal erfolgreich angewendet.
  Der erste erreichbare API-Test erzeugte eine zu lange Zusammenfassung; diese
  wurde verworfen und der ursprüngliche Kontext vollständig beibehalten. Die
  Längenvorgabe wurde anschließend um eine kürzere Ziellänge ergänzt.
- Der anschließende Live-Test mit synthetischen Daten über `gpt-5-mini` bestand
  Verdichtung, Wiederverwendung ohne erneuten API-Aufruf und Faktenabruf:
  korrigierter Zieltermin, unverbindlicher Status, ausstehende Rückmeldung,
  geänderter Kontakt, ursprünglicher Bezug von „morgen“ und keine erfundene
  Kalenderaktion. Geschätzte Historie: **3150 → 1721 Tokens**. Tatsächliche
  API-Nutzung: Zusammenfassung 1802 Input-/650 Output-Tokens, anschließende
  Antwort einschließlich Systemprompt 5132 Input-/232 Output-Tokens.
  Es wurden keine echten Gesprächs- oder Kalenderdaten verwendet. Das belegt
  diesen begrenzten Fall, keine allgemeine Qualität über viele Verdichtungen.
  Nächster Schritt: lange reale Unterhaltungen auf verlorene Zusammenhänge,
  Korrekturen und Kosten beobachten. Docker-/Proxmox-Betrieb blieb ungeprüft.

Verifikation der eigenständigen Zeitbewertung am 09.11.2026:

- `tests/test_evaluation.py`, `tests/test_thread_tools.py`, `tests/test_follow_up.py`,
  `tests/test_worker.py` und `tests/test_dates.py`: **56 Tests bestanden**, keine
  übersprungen. Geprüft wurden unter anderem der Bewertungskontext mit
  zurückgestellten Vorhaben, die weiterhin wirksame Hinweispause in temporären
  PostgreSQL-Datenbanken sowie Werkzeug-, Datums- und Worker-Anbindung.
- Modellantworten waren simuliert. Die gemeinsamen Anweisungen zur Kritikalität
  sind damit technisch eingebunden; die Qualität der eigenständigen Einschätzung
  und das Ausbleiben unnötiger Rückfragen sind noch nicht live nachgewiesen.
  Nächster Schritt: echte Gespräche und geplante Auswertungen auf begründete,
  rechtzeitige Hinweise und unnötige Wiederholungen beobachten.

Verifikation der Webrecherche am 07.11.2026:

- `tests/test_web_research.py`, `tests/test_web.py`, `tests/test_thread_tools.py`,
  `tests/test_calendar_search.py`, `tests/test_evaluation.py` und
  `tests/test_config.py`: **107 Tests bestanden**. Abgedeckt sind gemischte
  native Web-/lokale Funktionsaufrufe, Abschaltung, rundenübergreifendes Budget,
  fehlgeschlagene Antworten, Quellenpersistenz im Antworttext und sichere Links
  in gerenderten Chat-/Vorschlags-/Vorhabenseiten. Dienste und Speicher waren gemockt.
- Zwei echte Läufe von `scripts/check_web_research.py` über den zentralen
  Agenten mit `gpt-5-mini`, ohne lokale Funktionswerkzeuge: jeweils eine erfolgreiche
  native Websuche. Antwort: nächste Red Bull Romaniacs **27.–31. Juli 2027** mit
  offizieller Veranstalterquelle. Der zweite Lauf nach Korrektur doppelter Links
  lieferte genau einen Quellenverweis und meldete 11.132 Input-/313 Output-Tokens.
  Der Termin wurde zusätzlich gegen die
  [offiziellen Veranstaltungsregeln](https://www.redbullromaniacs.com/for-competitors/romaniacs-event-regulations)
  geprüft. Keine gespeicherten Gespräche, Vorhaben oder Kalendertermine verändert.
- Damit ist öffentliche Recherche über Hugos Modellpfad live belegt. Ein
  unbeaufsichtigter Worker-Lauf mit hilfreicher Webrecherche, die Verlässlichkeit
  bei widersprüchlichen Quellen und der künftige Docker-/Proxmox-Betrieb sind
  dadurch noch nicht nachgewiesen. Nächster Betriebsschritt: Recherchebedarf,
  Quellenqualität, Wiederholungen und Verbrauch bei realen Auswertungen beobachten.

Verifikation am 07.11.2026: `tests/test_calendar_search.py`,
`tests/test_thread_tools.py`, `tests/test_evaluation.py` und `tests/test_dates.py`
liefen mit **62 bestandenen Tests**. Die neue Kalendersuche wurde vom
Agentenwerkzeug bis zu simulierten Google-Antworten geprüft, einschließlich
mehrerer Kalender und Ergebnisseiten, mehr als 100 Treffern, Berliner
Jahreswechsel, ganztägiger Termine, fehlender Leserechte und API-Fehler.
Google-Serienauflösung und Textsuche werden über die API-Parameter angefordert;
zum Zeitpunkt dieses Tests waren ihr tatsächliches Verhalten und die
selbstständige Werkzeugwahl des Modells noch nicht live verifiziert.

Ergänzende Kalenderdiagnose am 07.11.2026:

- Live reproduziert: Unkodierte `#`-Zeichen in Kalender-IDs verursachten HTTP 404
  bei Feiertagen und Kalenderwochen und brachen die kalenderübergreifende Suche ab.
  Mit kodierten IDs waren dieselben Kalender lesbar. Alle Kalender-/Terminpfade
  kodieren ihre IDs jetzt, einschließlich Einzelabruf und freigegebener Änderungen.
- Die echte Google-Textsuche fand einen bekannten Termin im Folgejahr mit einem
  Teilbegriff; die zusammengeschriebene Anfrage fand den getrennt geschriebenen
  Titel nicht. Die Suche bleibt eine Textsuche; das Modell muss Varianten wählen.
- Der direkte korrigierte Werkzeugpfad fand den Termin bei einer vollständigen
  Suche über zehn aktuell gelistete Kalender. Ein erster Modelllauf mit dem
  bisherigen Prompt hörte dagegen nach einem leeren Ergebnis auf. Der Prompt
  fordert deshalb jetzt ausdrücklich eigenständige Suchvarianten vor Rückfragen;
  Modell und Reasoning-Einstellung bleiben unverändert. Grundlage für klare
  Such- und Abbruchbedingungen: [OpenAI Docs: GPT-5 prompting guide](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide#controlling-agentic-eagerness).
- Der anschließende Live-Modelllauf mit derselben Frage suchte eigenständig
  auch nach der getrennten Schreibweise und nannte den richtigen Kalendertermin
  mit Beginn und Ende. Verwendet wurden der reguläre Systemprompt und Tool-Loop,
  ausschließlich `search_events`/`list_calendars`, ohne Websuche oder gespeicherte
  Gesprächshistorie. Das belegt diesen konkreten Fall, keine allgemeine Trefferquote
  oder bereits erfolgte Übernahme auf Proxmox.
- `tests/test_calendar_client.py` und `tests/test_calendar_search.py`: **23 Tests
  bestanden**, einschließlich HTTP-URL-Prüfung mit `#`, `/`, `?` und `%` in IDs.
  Schreiboperationen wurden nur simuliert; keine externen Termine verändert.

Gezielt Start, Migration und Anmeldung prüfen:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_migrations.py tests/test_config.py tests/test_worker.py tests/test_auth.py tests/test_auth_storage.py tests/test_web.py
```

### Docker-Smoke-Test

```powershell
docker build -t hugo:local .
$env:HUGO_DOCKER_SMOKE = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_docker_smoke.py -q
Remove-Item Env:HUGO_DOCKER_SMOKE
```

Der Test verwendet ein isoliertes Compose-Projekt mit Testzugängen und prüft:

- Start und Anmeldung
- Schreibrechte im Modellcache
- Ausgehenden Worker-Zugriff
- Sitzungserhalt nach Migration und Neuerstellen der Container

Die Testvolumes werden anschließend entfernt.

### Manuelle Diagnosewerkzeuge

Mit aktivierter virtueller Umgebung im Projektordner:

```bash
python scripts/check_embeddings.py
python scripts/check_google_calendar.py
```

| Skript | Verhalten |
|---|---|
| `check_embeddings.py` | Vergleicht Beispielsätze im Speicher; keine Datenbankeinträge |
| `check_google_calendar.py` | Liest `credentials.json`, schreibt `token.json` und listet Termintitel |
| `check_web_research.py` | Öffentliche Romaniacs-Frage über Hugos Recherchepfad; keine DB-/Kalenderwerkzeuge, echte API-Kosten |
| `check_chat_context.py` | Verdichtung und Faktenabruf mit erfundenem Verlauf, Korrekturen und relativen Daten; prüft Cache-Wiederverwendung, keine DB-/Kalenderzugriffe, echte API-Kosten |
| `check_chat_focus.py` | Zwei Modellproben für kurze Zeitplanung und Terminkonflikte mit erfundenen Werkzeugdaten; keine DB-/Kalenderzugriffe, echte API-Kosten |

Begrenzten Webrecherche-Live-Test im Projektordner ausführen:

```powershell
.venv/Scripts/python.exe scripts/check_web_research.py
```

`--question` erlaubt eine andere öffentliche Testfrage. Das Skript lädt die
Projekt-`.env`, verwendet höchstens drei Modellrunden und das konfigurierte
Webbudget. Es protokolliert native Webaktionen und Tokenverbrauch und gibt die
Antwort mit Quellen aus. Es verändert keine gespeicherten Gespräche oder Termine.

Der Embedding-Test kann das Modell herunterladen. Das Google-Skript benötigt separat `google-auth-oauthlib` und `google-api-python-client`. Die Anwendung selbst verwendet den OAuth-Weg unter `/ui/kalender`.

### Häufige Probleme

| Problem | Prüfung |
|---|---|
| Login hängt | Datenbank und Verbindungsadresse prüfen: lokal `127.0.0.1`, im Docker-Stack `db` |
| Login führt erneut zur Anmeldung | Bei lokalem HTTP Secure-Cookie deaktivieren; Hostname beibehalten |
| HTTP 403 hinter Proxy | Host, Origin, `X-Forwarded-Proto` und Proxy-Vertrauen prüfen |
| HTTP 503 bei Anmeldung | Passwort-Hash prüfen und Webprozesse vollständig neu starten |
| Env-Werte werden nicht übernommen | Prozessvariablen prüfen; Docker-Container mit `up` neu erstellen |
| Port 8000 belegt | Server beenden oder `--port` beziehungsweise `WEB_PORT` verwenden |
| Migration fehlgeschlagen | Logs und Exitcode prüfen; keine Historienzeilen löschen |
| Keine Vorschläge | Auswertung auslösen, Worker und `evaluation_runs` prüfen |
| Worker erreicht APIs nicht | Netzwerk und API-Schlüssel prüfen |
| Erster Start dauert lange | Bibliotheksimporte, Modell-Download, Cache und RAM prüfen |
| Chatantwort leer | Modellstatus und Tokenverbrauch prüfen |
| Speicherplatz knapp | Daten-, Volume-, Backup- und Loggrößen prüfen |

Ein Reasoning-Modell kann sein Ausgabelimit für Reasoning verbrauchen. Der Agent verwendet niedrigen Reasoning-Aufwand und diagnostiziert unvollständige oder leere Antworten.

Für Docker-Diagnosen `ps -a`, Service-Logs, `/health` und eine Anmeldung prüfen. Keine Schlüssel oder Sitzungstokens protokollieren.

Fehlerberichte: [GitHub Issues](https://github.com/jhohmann/hugo/issues).

## Grenzen und Weiterentwicklung

### Grenzen

- Ein Nutzer und ein Worker; keine getrennten Arbeits-/Privatkonten.
- Erinnerungsupdates nur für den Status `proposed`.
- Ereignis-, Handlungs- und Deadline-Felder lassen sich über Agentenwerkzeuge nicht leeren.
- Semantisch ähnliche Vorschläge können trotz exakter Duplikatprüfung erneut erscheinen.
- Begrenzte Listen ohne vollständige Seitennavigation.
- Keine automatischen Gesprächstitel und keine Push-Benachrichtigungen.
- Paketversionen sind teilweise nicht festgelegt; Builds sind nicht bitgenau reproduzierbar.
- Proxmox-Betrieb, Wiederherstellung und externe Kalenderabläufe benötigen Prüfungen in der jeweiligen Zielumgebung.

### Weiterentwicklung

| Bereich | Themen |
|---|---|
| Zeitplanung | Abhängigkeiten und die Qualität von Wiedervorlagen und Vorbereitungsfenstern |
| Proaktivität | Relevante tägliche Hinweise, weniger Wiederholungen, geeignete Zustellkanäle |
| Kalender | Verfügbarkeit in Auswertungen, Wiederholungen, ganztägige und abgesagte Termine |
| Aktionen | Allgemeines Freigabe- und Ausführungssystem mit nachvollziehbarem Verlauf |
| Betrieb | HTTPS, Backup-Restore, Update-Rollback, Monitoring und Verbrauchskontrolle |

Arbeits-/Privattrennung ist ein mögliches Ausbauziel. Mail ist als zukünftige
Verbindung vorgemerkt; Art und Umfang des Zugriffs sind noch offen.

API-Kosten hängen von Nutzung, Modell und Kontext ab. Bei Modellaufrufen wird relevanter Kontext an den Anbieter übertragen.

## Technische Referenzen

- [Compose-Startreihenfolge](https://docs.docker.com/compose/how-tos/startup-order/)
- [Compose up](https://docs.docker.com/reference/cli/docker/compose/up/)
- [PostgreSQL Advisory Locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS)
- [Python scrypt](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt)
