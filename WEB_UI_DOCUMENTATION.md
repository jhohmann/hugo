# Hugo Web-UI – MVP 0.1 Dokumentation

**Status:** ✅ Vollständig implementiert und getestet (seit 2026-11-03)

## Überblick

Hugo verfügt über eine schlanke, **servergeseitig gerenderte Weboberfläche** mit drei Hauptseiten: **Chat**, **Heute** (Vorschläge) und **Vorhaben** (Threads). Die Oberfläche funktioniert vollständig ohne externe CDN-Abhängigkeiten und mit minimalem JavaScript.

### Technische Merkmale

- **Framework:** FastAPI + Jinja2 (serverseitig gerendert)
- **Styling:** Vanilla CSS mit Light/Dark Mode (prefers-color-scheme)
- **JavaScript:** Minimal – nur für Komfort (Laden, Bestätigung, Enter-zum-Senden)
- **Tests:** 64 Unit-Tests bestehen; Web-UI-Tests verwenden Mocking statt Live-Datenbank
- **Responsive:** Desktop und Smartphone optimiert
- **Kein Build-Schritt:** Ready to go

---

## Start und Zugang

### Voraussetzungen

1. **Python 3.12+** mit venv
2. **Docker** (für PostgreSQL)
3. **Abhängigkeiten installiert:**
   ```bash
   cd /workspaces/hugo
   .venv/bin/pip install -r backend/requirements.txt
   ```
4. **OpenAI API-Schlüssel** gesetzt: `export OPENAI_API_KEY=...`

### Server starten

```bash
# Datenbank starten (Schema und Migrationen laufen automatisch)
docker compose up -d db

# Im backend-Verzeichnis den Server starten
cd /workspaces/hugo/backend
OPENAI_API_KEY=sk-... ../..venv/bin/python -m uvicorn app.main:app --port 8000

# Weboberfläche erreichbar unter:
# http://localhost:8000/ui
```

### Navigation

- **Heute** (`/ui/heute`): Startseite – Vorschläge und Überblick für heute
- **Chat** (`/ui/chat`): Gesprächsverlauf und Kommunikation mit Hugo
- **Vorhaben** (`/ui/threads`): Threads gruppiert nach Status

---

## Funktionen

### 1. Chat (`/ui/chat`)

**Zweck:** Direkter Dialog mit Hugo; alle inhaltlichen Änderungen erfolgen hier.

**Funktionen:**
- ✅ Neue Unterhaltung beginnen oder bestehende fortsetzen
- ✅ Gesprächsverlauf mit vollständigen Nachrichten anzeigen
- ✅ Links die Liste der 50 jüngsten Unterhaltungen mit Vorschau (erste Nutzernachricht)
- ✅ Ladezustand während Hugos Antwort ("Hugo denkt nach …")
- ✅ Fehlerbehandlung: Bei Fehler bleibt der Entwurf erhalten
- ✅ Enter sendet, Shift+Enter erstellt Zeilenumbruch (ohne JS: nur Submit-Button)

**Architektur:**
- Route: `GET /ui/chat`, `GET /ui/chat/{conversation_id}`, `POST /ui/chat`
- Service: `app.chat_service.run_chat()` (geteilt mit JSON-API `/chat`)
- Storage: `app.storage.database` (Unterhaltungen, Nachrichten)
- Agent: `app.agent.assistant.ask_hugo()` (zentral, Tool-Schleife)

**Technische Details:**
- Form-basiert (HTML multipart/form-data), kein AJAX
- Bei erfolgreichem Send: Redirect zu `/ui/chat/{new_id}`
- Entwürfe werden im Fehlerfall im Formular beibehalten
- JavaScript: Auto-Scroll zum Ende, Enter-Handling, Ladezustand

---

### 2. Heute (`/ui/heute`)

**Zweck:** Überblick über Tagesaufgaben und Vorschläge von Hugo.

**Funktionen:**
- ✅ **Offene Vorschläge** anzeigen mit:
  - Priorität (P1–P5, visuell unterschieden)
  - Bezug zu Vorhaben (anklickbar zu `/ui/threads/{id}`)
  - Vorgeschlagenes Datum mit Dringlichkeitshinweis ("heute", "morgen", "in 5 Tagen", "seit 2 Tagen")
  - Grund/Begründung (falls vorhanden)
- ✅ **Drei Aktionen pro Vorschlag:**
  - **Bestätigen:** Status → `confirmed`, Vorschlag verschwindet aus offener Liste
  - **Zurückstellen:** Status → `deferred`, erscheint in aufklappbarer "Zurückgestellt"-Sektion
  - **Verwerfen:** Status → `dismissed`, wird nicht wiederholt (außer bei neuer Auswertung)
- ✅ **Zurückgestellt-Sektion:** Einklappbar, zeigt alle deferrierten Vorschläge
- ✅ **Manual Evaluation Trigger:** "Jetzt auswerten"-Button
  - Startet `POST /proactivity/evaluate`
  - Zeigt letzte Auswertungszeit und Status
- ✅ **Tagesanzeige:** Datum und Wochentag (Berlin-Zeit)

**Architektur:**
- Route: `GET /ui/heute`, `POST /ui/suggestions/{id}`, `POST /ui/evaluate`
- Storage: `app.storage.suggestions` (list, update_suggestion_status)
- Storage: `app.storage.threads` (Thread-Titel für Vorschlag-Links)
- Tools: `app.tools.dates` (today_berlin, relative_label, urgency_class)
- Agent: `app.agent.evaluation.run_evaluation()` (bei "Jetzt auswerten")

**Visuelles Design:**
- Oberste Vorschläge (offen): Weiße Karten mit Prioritätsbalken links
- Wichtige Vorschläge (P≥4): Linke Borderlinie in Rot
- Zurückgestellt: Grauere Darstellung in Expandable Section
- Farbcodes für Dringlichkeit: Rot (überf.), Orange (bald), grau (später)

**Technische Details:**
- Vorschläge werden beim Abrufen als "surfaced" gekennzeichnet (nur pending → surfaced)
- Suggestions enthalten: `content`, `priority`, `reason`, `suggested_date`, `thread_id`, `status`, `delivery`
- Form-basiert, kein AJAX; Bestätigung erfolgt mit JavaScript-Dialog bei "Verwerfen"

---

### 3. Vorhaben (`/ui/threads`)

**Zweck:** Übersicht aller Handlungsstränge und ihrer Fortschritte.

**Funktionen auf der Übersichtsseite:**
- ✅ Threads gruppiert nach Status:
  - **Aktiv** / **Wartet** / **Idee** (offen angezeigt)
  - **Erledigt** / **Archiviert** (in Accordion-Sektion, einklappbar)
- ✅ Pro Thread angezeigt:
  - Titel (anklickbar zur Detailseite)
  - Nächster Schritt (falls vorhanden)
  - Status-Label (Aktiv, Wartet, Idee, Erledigt, Archiviert)
  - Priorität (P1–P5, falls gesetzt)
  - Ereigniszeitraum (Startdatum oder Start–End, ca. Hinweis falls approx.)
  - "Handeln bis" Datum (Hugos Empfehlung, `act_by`)
  - Deadline (falls gesetzt)

**Detailseite `/ui/threads/{id}`:**
- ✅ Volles Thread-Profil:
  - Titel, Beschreibung
  - Status + Priorität + Labels
  - Ereigniszeitraum mit Originaltext (falls ca.)
  - Deadline mit Dringlichkeit
  - "Handeln bis" mit "Hugos Empfehlung"-Label
  - Nächster Schritt
  - Erstellt-/Geändert-Zeitstempel (Berlin-Zeit)
- ✅ **Zugehörige Vorschläge:** Alle Suggestions mit `thread_id == {id}` angezeigt
  - Offene Vorschläge: interaktiv (Bestätigen/Zurückstellen/Verwerfen)
  - Abgeschlossene: grau, informativ
  - "Zurück"-Link zum Thread bleiben nach Aktion erhalten

**Architektur:**
- Routes: `GET /ui/threads`, `GET /ui/threads/{thread_id}`
- Storage: `app.storage.threads` (list_threads, get_thread)
- Storage: `app.storage.suggestions` (list_suggestions gefiltert auf thread_id)
- Formatting: `app.web.formatting` (thread_status_label, event_range_text, urgency_class, relative_label)

**Visuelles Design:**
- Thread-Reihen: Titel + nächster Schritt links, Meta-Daten (Status, Datum) rechts
- Datenhinweise farbcodiert: Rot (überfällig), Orange (bald), grau (später)
- Detailseite: Tabellarisches Layout (dt: dd) für Fakten
- Breitcreen: Two-Column-like; Smartphone: gestacked

**Technische Details:**
- Threads erhalten `COALESCE(act_by, event_start, deadline)` Sortierung (nächste Action zuerst)
- Zeit-Präzision: `exact` oder `approximate`; bei approx. wird `time_text` (Original) angezeigt
- `event_start`, `event_end` sind DATE ohne Tageszeit; `deadline`, `act_by` auch
- Datums-Hinweise berechnet: `days_until(date, today)` → "heute", "morgen", "in N Tagen", "seit N Tagen"

---

## Styling und Benutzerfreundlichkeit

### Farbschema

**Light Mode (Standard):**
- Hintergrund: `#f6f7f9` (hell grau)
- Flächen: `#ffffff` (weiß)
- Text: `#1c1e21` (dunkel)
- Akzent: `#2563eb` (Blau)
- Gefahr: `#b91c1c` (Rot)
- OK: `#15803d` (Grün)
- Warnung: `#b45309` (Orange)

**Dark Mode (auto mit `prefers-color-scheme`):**
- Hintergrund: `#14171b`
- Flächen: `#1d2127`
- Text: `#e5e7eb`
- Farben angepasst für Kontrast

### Responsive Design

- **Desktop (>760px):**
  - Chat: Sidebar links (260px) + Nachrichten rechts
  - Breite Metadaten-Reihen
- **Smartphone (≤760px):**
  - Chat: Sidebar ausgeklappt → oben
  - Single-Column Layout
  - Kleinere Schriftgrößen
  - Conversation Panel standardmäßig eingeklappt

### Accessibility

- ✅ Semantisches HTML (nav, header, main, section, article, dl/dt/dd)
- ✅ `aria-label`, `aria-current="page"` für Navigation
- ✅ `aria-live="polite"` für dynamische Nachrichtenlisten
- ✅ Visually-Hidden Labels für Screen Reader
- ✅ Farbcodierung + Text-Labels (keine nur-Farb-Info)
- ✅ Tastaturnavigation: Enter-Handling, Focus-Management

---

## JavaScript (Minimal)

**Datei:** `/static/app.js` (~60 Zeilen)

**Funktionen:**
1. **Loadingzustand:**
   - Formen mit `data-loading-text` Attribut: Button wird deaktiviert, Text wird angezeigt
   - Zeiger für `<div class="loading-indicator">`
2. **Bestätigungsdialog:**
   - Formen mit `data-confirm` Attribut: `window.confirm()` vor Submit
   - Für destruktive Aktionen (Verwerfen)
3. **Chat-Verbesserungen:**
   - Auto-Scroll zum Ende der Nachrichtenliste
   - Enter sendet, Shift+Enter bricht Zeile um
   - Chat-Input fokussiert bei Seitenladezeit

**Fallback ohne JavaScript:**
- ✅ Alle Funktionen arbeiten (nur ohne visuelle Verbesserungen)
- ⚠️  Fehlender: Ladeanzeige, Bestätigungsdialog (Button sendet direkt), Enter-Handling

---

## API-Endpunkte (Web-UI nutzt diese)

Neue Read-Only Endpoints (für Web-UI):
- `GET /conversations` — Jüngste Unterhaltungen mit Preview
- `GET /conversations/{id}/messages` — Nachrichten einer Unterhaltung
- `GET /threads` — Alle Threads (optional: `?status=active`)
- `GET /suggestions` — Offene Vorschläge (mit `mark_surfaced=True`)

Bestehende Endpoints (unverändert):
- `POST /chat` — Chat-API (auch von Web-UI genutzt)
- `POST /proactivity/evaluate` — Manuelle Auswertung
- `GET /proactivity/runs` — Evaluations-Audit-Log
- `PATCH /suggestions/{id}` — Status ändern

Alle Web-UI Routes sind mit `include_in_schema=False` ausgeblendet; Swagger UI `/docs` zeigt nur JSON-API.

---

## Dateistruktur

```
backend/app/web/
├── routes.py              # Web-UI Routen (7 GET, 3 POST)
├── formatting.py          # Formatierungshilfen für Templates
├── templates/
│   ├── base.html          # Layout-Basis
│   ├── chat.html          # Chat-Seite
│   ├── heute.html         # Vorschlag-Übersicht
│   ├── threads.html       # Thread-Übersicht
│   ├── thread_detail.html # Thread-Detailseite
│   ├── thread_row.html    # Wiederverwendbare Thread-Karte
│   └── error.html         # Fehlerseite
└── static/
    ├── style.css          # Styling (responsive, 500 Zeilen)
    └── app.js             # Minimal JS (60 Zeilen)
```

---

## Bekannte Einschränkungen (MVP 0.1)

✅ **Implementiert:**
- Server-gerenderte Oberfläche
- Drei Hauptseiten (Chat, Heute, Vorhaben)
- Responsive Design
- Dark Mode
- Fehlerbehandlung und Ladezustände
- Prioritäts- und Dringlichkeitshints

⚠️ **Nicht im Scope:**

| Funktion | Grund | Roadmap |
|----------|-------|---------|
| Authentifizierung | Lokal/vertrauenswürdig | Später (vor produktiven Einsatz) |
| Automat. Benachrichtigungen | Scheduler fehlt noch | Phase 2 (tägliche Evaluation) |
| Google Calendar Integration | Separate Phase | Nach Vorschlag-Engine stabil |
| Benutzerverwaltung | Multi-Tenant komplex | Später |
| WebSockets/Real-time | Form-basiert pragmatisch | Optional |
| Conversation-Titel | Automatisches Naming? | Optional |

**Warum nur Manual Evaluation?**
- Die Vorschlag-Engine funktioniert nur bei explizitem Aufruf
- Ein Scheduler (`daily_evaluation()`) ist noch nicht implementiert
- Geplant: Cron-Job oder Async-Worker in der nächsten Phase

---

## Tests

### Laufen Sie die Tests aus

```bash
cd /workspaces/hugo
python -m pytest tests/ -v
```

### Ergebnis

```
====== 64 passed, 27 skipped in 10.52s ======
```

- **Passed:** 64 (Unit-Tests, Web-Routing, Mocking)
- **Skipped:** 27 (erfordern Live-Datenbank; ohne DB übersprungen)

### Test-Coverage

`tests/test_web.py` deckt ab:
- ✅ Chat-Seiten (neu, fortsetzen, Fehler)
- ✅ Heute-Seite (Vorschläge, Aktionen)
- ✅ Vorhaben-Seiten (Übersicht, Detail)
- ✅ Fehlerbehandlung (404, 400)
- ✅ Navigation und Statuszähler

Storage/Agent werden gemockt → kein DB/API-Zugang nötig.

---

## Performance und Optimierungen

- **Lazy Loading:** Deferierte Vorschläge in `<details>` (einklappbar)
- **Pagination:** `limit`-Parameter auf allen Listenseiten
- **DB-Queries:** Minimal; Vorschlag-Thread-Titel nur bei Bedarf geladen
- **CSS:** Inline, keine Minifizierung (500 Zeilen), unterstützt viele Browser
- **JS:** Optional; alle Funktionen arbeiten auch ohne

---

## Nächste Schritte (nach MVP 0.1)

1. **Scheduler implementieren**
   - Täglich 8:00 Uhr Auswertung
   - Vorschläge via Weboberfläche anzeigen oder E-Mail

2. **Google Calendar Integration**
   - Termine als Quelle der Wahrheit lesen
   - Konflikte in Vorschlägen erkennen

3. **Deployment**
   - Docker-Image bauen
   - Authentifizierung (einfach: Auth0, Keycloak oder API-Key)
   - Reverse Proxy (nginx)
   - Monitoring (error logs)

4. **Polishing**
   - Conversation-Titel
   - WYSIWYG-Editor für Beschreibungen (optional)
   - Export/Druck von Threads

---

## Zusammenfassung

Die Hugo Web-UI ist **produktionsreif für lokale / vertrauenswürdige Umgebungen**. Sie ist:

✅ **Schlank:** Keine Abhängigkeiten außer FastAPI, Jinja2  
✅ **Wartbar:** Reines HTML/CSS/JS, serverseitig gerendert  
✅ **Zuverlässig:** 64 Tests, bewährte Patterns  
✅ **Responsiv:** Desktop ↔ Smartphone  
✅ **Zugänglich:** Semantisches HTML, Dark Mode, ohne JS nutzbar  

**Nächster Test:** Nach DB-Start unter `/ui` aufrufen und durchprobieren!
