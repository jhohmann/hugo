# Next: Internetrecherche für Hugo

Aktueller Auftrag vom 07.11.2026: Hugo soll selbstständig aktuelle öffentliche
Informationen recherchieren können, beispielsweise Veranstaltungstermine wie
die Red Bull Romaniacs. Dieser Plan hat Vorrang vor dem unten erhaltenen
Zeitleistenplan. Technische Betriebsdokumentation und Prüfergebnisse gehören
weiterhin in [README.md](README.md).

## Ergebnis und Grenzen

- Der zentrale Agent entscheidet anhand der Frage oder eines relevanten
  Vorhabens, wann eine Webrecherche nötig ist, und verwendet die native
  `web_search` der bestehenden OpenAI Responses API.
- Antworten nennen belastbare Quellen mit anklickbaren Links. Bei Terminen
  Edition/Jahr, Austragung und Anmeldefrist unterscheiden; bevorzugt offizielle
  Veranstalterseiten prüfen. Fehlende oder widersprüchliche Angaben bleiben
  ausdrücklich ungesichert.
- Eine recherchierte Veranstaltung ist keine Teilnahmezusage. Webseiten sind
  Daten, keine Anweisungen. Keine automatischen Kalenderänderungen oder
  Nachrichten; vorhandene Freigabegrenzen bleiben wirksam.
- Keine zusätzliche Agentenpipeline, kein eigener Crawler und keine
  veranstaltungsspezifischen Python-Regeln. Der vorhandene API-Schlüssel wird
  verwendet; Recherche lässt sich abschalten und pro Lauf begrenzen.

## Umsetzung und Prüfung

- [x] Bestehenden Agenten, UI, Dokumentation und offizielle API-Dokumentation
  prüfen; bisherigen Zeitleistenplan erhalten.
- [x] Native Websuche im zentralen Tool-Loop für Chat und proaktive Auswertung
  verfügbar machen; Budget, Fehlerbehandlung und Protokollierung ergänzen.
- [x] Rechercheanweisungen für aktuelle Quellen, Jahresbezug, Unsicherheit und
  vertrauliche Daten ergänzen. Recherche nur bei konkretem Bedarf.
- [x] API-Quellenannotationen als dauerhafte Links in Antworten erhalten und
  in Chat/Vorschlägen sicher darstellen, ohne unkontrolliertes HTML auszuführen.
- [x] Automatisierte Tests für gemischte Web-/Funktionsaufrufe, Quellen,
  Abschaltung, Budget und sichere Linkdarstellung ausführen.
- [x] Einen begrenzten Live-Test mit öffentlicher Romaniacs-Frage über Hugos
  eigenen Recherchepfad ausführen; keine privaten Daten oder Schreibwerkzeuge.
- [x] README und diesen Plan mit Ergebnissen, Grenzen und nächstem Schritt
  aktualisieren.

**Abnahme:** Eine aktuelle öffentliche Frage kann eine echte Websuche auslösen
und eine quellenbelegte Antwort liefern. Fehler dürfen nicht als erfolgreiche
Recherche erscheinen. Automatisierte Tests und Live-Nachweis werden getrennt
dokumentiert; ein manueller Lauf belegt noch keinen unbeaufsichtigten Betrieb.

**Stand 07.11.2026: Umsetzung abgeschlossen.** 107 automatisierte Tests bestanden;
zwei Live-Recherchen über Hugos zentralen Agenten bestätigten die öffentliche
Romaniacs-Frage mit offizieller Quelle. Die im ersten Lauf beobachtete doppelte
Quellenanzeige ist korrigiert und durch Regressionstest sowie zweiten Live-Lauf
geprüft. Details, Konfiguration und Grenzen stehen in der
[README](README.md#internetrecherche), die Nachweise unter
[Tests und Diagnose](README.md#tests-und-diagnose).

**Nächster Betriebsschritt:** Bei realen geplanten Auswertungen prüfen, ob Hugo
nur bei konkretem Bedarf recherchiert, passende aktuelle Quellen verwendet und
unnötige Wiederholungen vermeidet. Das ist Betriebsbeobachtung, kein bereits
erbrachter Nachweis autonomer Proaktivität. Der Zeitleistenplan unten bleibt als
separates, noch nicht abgeschlossenes Vorhaben erhalten.

---

# Zurückgestellter Plan: Git-inspirierte Zeitleiste für Hugos Handlungsstränge

## Ziel

Die Ansicht **Vorhaben** erhält eine interaktive, Git-Branch-inspirierte Zeitleiste, die **Vergangenheit und Zukunft** auf einer gemeinsamen, proportionalen Zeitachse darstellt. Jeder Handlungsstrang besitzt eine eigene horizontale Spur. Der Nutzer erkennt auf einen Blick, wie sich Vorhaben entwickelt haben, wo Pausen liegen und welche Termine, Fristen und möglichen nächsten Schritte anstehen.

Die Zeitleiste ist zunächst eine **rein lesende Planungs- und Orientierungsansicht**. Sie verändert weder Agentenverhalten noch vorhandene Daten. Die bestehende Listenansicht bleibt erhalten.

## Grundprinzipien

- Git dient als **visuelle Inspiration**, nicht als Datenmodell: keine künstlichen Commits, Branches oder Merges.
- Eine gemeinsame horizontale Zeitachse mit **Heute-Markierung**; Abstände sind proportional zur tatsächlichen Zeit.
- Vergangenheit als durchgezogene Spur, Zukunft als dezente gestrichelte Fortsetzung.
- Titel und Status links fixiert; Klick auf den Titel öffnet die bestehende Detailansicht.
- Tatsächlich erfasste Ereignisse, bestätigte Termine und bloße Vorschläge sind klar unterscheidbar.
- **Hugo-Vorschläge dürfen niemals wie verbindliche Termine wirken.**
- Keine historischen Ereignisse oder Abschlussdaten aus `updated_at` rekonstruieren.

## Ein- und ausblendbare Informationsebenen

Die folgenden Ebenen können **unabhängig voneinander** ein- und ausgeblendet werden:

1. **Aktivitäten / Vergangenheit:** Anlage des Handlungsstrangs, zugeordnete Chatnachrichten und später explizit protokollierte Entscheidungen oder Meilensteine.
2. **Geplante Zeitpunkte:** vorhandene, dem Handlungsstrang eindeutig zugeordnete Termine und geplante Schritte, einschließlich zukünftiger Kalenderereignisse, sofern eine belastbare Zuordnung existiert.
3. **Deadlines:** vorhandene Fristen mit eindeutigem Datum; visuell auffälliger als allgemeine Zeitpunkte.
4. **Hugos Ideen:** Vorschläge, Erinnerungsimpulse und mögliche Zeitfenster; visuell zurückhaltend, ausdrücklich als *Vorschlag* gekennzeichnet.

Standardmäßig sind alle Ebenen sichtbar. Filterzustände und gewählter Zeitraum sollen in der URL abbildbar sein. Vorschläge dürfen die Anzeige „letzte Nutzeraktivität“ **nicht** aktualisieren.

## Herkunft und Verbindlichkeit

Jeder dargestellte Punkt erhält, soweit aus der Quelle bestimmbar:

- **Herkunft:** Nutzer, Kalender oder Hugo.
- **Verbindlichkeit:** bestätigt, geplant oder vorgeschlagen.
- **Zeitbezug:** Ereigniszeitpunkt, Terminzeitpunkt oder Frist.
- **Quellverweis:** Link zur Nachricht, zum Vorhaben, Kalenderereignis oder Vorschlag, sofern verfügbar.

Keine Eigenschaften erraten. Fehlen Daten oder ist die Zuordnung unsicher, das Ereignis nicht als verbindlich darstellen. Insbesondere **keine Zuordnung von Kalenderereignissen oder Nachrichten nur anhand von Stichwörtern**.

## Vorhandene Daten und Grenzen

Es existieren `threads`, `thread_messages`, `messages`, threadbezogene `suggestions` und das bereits implementierte `thread_events`-Protokoll mit lesendem Agentenwerkzeug. Belastbare historische Quellen sind:

| Quelle | Zeitpunkt | Bedeutung |
| --- | --- | --- |
| `thread_events.recorded_at` | Erfassungszeit | Relevante Änderungen mit Vorher-/Nachher-Werten und Herkunft |
| `threads.created_at` | Anlagezeit | Handlungsstrang erstellt |
| `messages.created_at` über `thread_messages` | Nachrichtenzeit | Nutzer-/Chataktivität, als Nachrichtenauszug bezeichnet |
| `suggestions.created_at` | Erstellzeit | Hugo-Vorschlag, **nicht** Nutzeraktivität |

Relevante Änderungen werden seit Migration 005 erfasst; für die Zeit davor existiert keine vollständige Historie. `updated_at` ist kein Ereignisprotokoll. Frühere Statuswechsel, Entscheidungen, Terminänderungen oder Abschlüsse nicht nachträglich erfinden. `conversation` als Ereignisherkunft belegt keine Nutzerentscheidung; für die letzte Nutzeraktivität werden zugeordnete Nachrichten mit `role='user'` verwendet. Nachrichten und ihre Änderungsereignisse nicht doppelt zählen.

**Vor der Implementierung** im aktuellen Repository prüfen, welche strukturierten Quellen für Termine, Deadlines, Planungszeitpunkte, Kalenderzuordnungen und Vorschlagsdaten tatsächlich existieren. Diese nur anbinden, wenn Datum, Thread-Zuordnung und Bedeutung zuverlässig verfügbar sind. Fehlt eine Quelle, die Ebene als leer/noch nicht verfügbar behandeln, nicht künstlich befüllen. Keine neue Persistenz oder Migration allein für die Visualisierung einführen.

Für die Visualisierung ist keine weitere Migration vorgesehen. `event_start`/`event_end` liefern geplante Zeiträume, `deadline` eine Frist. `act_by` ist Hugos Empfehlung, `review_on` ein interner Prüftermin. `suggested_date` ist ein Vorschlagsdatum, `deferred_until` lediglich dessen Wiedervorlage. Exakte Datumsangaben bedeuten nicht automatisch bestätigte Termine. Kalenderaktionen besitzen bisher keine explizite Thread-Zuordnung; reale Kalenderpunkte bleiben zunächst aus. Undatierte Vorschläge erhalten keinen erfundenen Zeitpunkt.

## Darstellung und Bedienung

- Eine Zeile je Handlungsstrang; offene Spuren reichen bis zum sichtbaren Planungshorizont, ohne einen Abschluss zu suggerieren.
- Bei abgeschlossenen Vorhaben nur dann ein Abschlussmarker, wenn das Abschlussdatum belegbar ist.
- Zoomstufen: 1 Monat, 3 Monate, 1 Jahr, gesamter relevanter Zeitraum; horizontales Scrollen, „Heute“-Taste.
- Der sichtbare Zeitraum umfasst bei Bedarf Vergangenheit **und** Zukunft; nicht auf historische Daten begrenzen.
- Aktivitätspunkte, geplante Zeitpunkte, Deadlines und Hugo-Ideen durch Form/Linienstil und Beschriftung unterscheiden, nicht nur durch Farbe.
- Nahe Ereignisse bei geringem Zoom gruppieren; Anklicken öffnet die Einzelereignisse.
- Tooltip/Detailansicht per Maus, Tastatur und Touch: Datum, Art, Herkunft, Verbindlichkeit, kurzer Quelltext und optionaler Link.
- Statusfilter: Aktiv (`proposed`, `active`, `waiting`), Inaktiv (`completed`, `archived`), Alle; zusätzlich vorhandene Tags Arbeit/Privat.
- Sortierung: standardmäßig älteste offene Vorhaben, alternativ längste Pause seit letzter **Nutzeraktivität**.
- Zeitformat Deutsch, Zeitzone `Europe/Berlin`; unbekannte Daten nicht als scheinbar genaue Zeitpunkte darstellen.
- Bei deaktiviertem JavaScript lesbare Liste der geladenen Ereignisse anbieten.

## Umsetzung im bestehenden Projekt

Die vorhandene FastAPI-/Jinja2-Oberfläche um `/ui/zeitleiste` ergänzen und aus „Vorhaben“ erreichbar machen. HTML, CSS und ein kleines lokales JavaScript-Modul verwenden; zunächst keine zusätzliche Bibliothek, kein CDN und kein Build-Schritt.

Voraussichtliche Dateien, an die aktuelle Repository-Struktur anpassen:

- `backend/app/web/templates/timeline.html`
- `backend/app/web/static/timeline.js`
- `backend/app/web/static/style.css`
- `backend/app/web/routes.py`
- `backend/app/web/templates/threads.html`
- `backend/app/storage/thread_timeline.py`
- `tests/test_timeline.py`

Daten für sichtbare Threads gebündelt laden, keine N+1-Abfragen. Zeitraum, Zeilenpagination und Punktgruppierung für größere Bestände berücksichtigen. Anzeige darf **keine** Vorschläge als gesehen markieren, Wiedervorlagen reaktivieren oder sonstige Zustände verändern. Die bestehende Navigation prüfen: Falls `_nav()` über `list_suggestions()` Seiteneffekte auslöst, für diese Ansicht eine rein lesende Alternative verwenden. Anmeldung und sicheres Escaping von Nachrichtentexten beibehalten.

## Vorgehen in Etappen

### 1. Optischer Prototyp – zuerst

Auf dem Entwicklungsbranch `feature/next-iteration` eine lokale Vorschau mit **klar gekennzeichneten Beispieldaten** erstellen. Keine Demodaten in PostgreSQL schreiben. Eine nur lokal aktivierbare Demoansicht (`/ui/zeitleiste?demo=1`) hinter bestehender Anmeldung anbieten.

Die Demo muss zeigen:

- kurze und mehrjährige Handlungsstränge, Aktivitätspausen und dichte Punktgruppen;
- vergangene Aktivitäten sowie zukünftige Termine und Deadlines;
- Hugo-Vorschläge, die sich unabhängig ausblenden lassen;
- Unterschied zwischen bestätigten, geplanten und vorgeschlagenen Zeitpunkten;
- verschiedene Status, lange Titel und schmale Browserfenster.

Zuerst das Erscheinungsbild und die Bedienung im Browser prüfen. **Noch keine produktiven Daten anbinden.**

### 2. Reale Daten anbinden

Quellen und Zuordnungen im Repository verifizieren. Vorhandene, zuverlässig zuordenbare Daten über denselben Renderer einlesen. Nicht verfügbare Zukunftsebenen transparent leer lassen. Keine Modellaufrufe beim Zoomen, Filtern oder Öffnen von Tooltips.

### 3. Bedienung und Skalierung

Gruppierung, Zoom, Touch-/Tastaturbedienung, URL-Filter, leere Datenbestände und große Zeiträume verfeinern.

### 4. Tests und Abnahme

Prüfen: korrekte Zeitpositionen und Zeitzonen, Filterkombinationen, Herkunft/Verbindlichkeit, Mehrfachzuordnungen, unbekannte Daten, Zugriffsschutz, Escaping und **unveränderte Datenbankzustände**. Browserprobe mit 100 Spuren und 5.000 Demoereignissen.

**Abnahmekriterium:** Auf einen Blick erkennbar sind vergangene Entwicklung, lange Pausen, anstehende Termine und Deadlines sowie davon klar getrennte Ideen von Hugo. Jede Informationsebene lässt sich einzeln ein- und ausblenden. Die Listenansicht bleibt nutzbar.

## Nicht Bestandteil dieser Iteration

- Automatische neue Planungen oder Änderungen an Hugos Agentenlogik.
- Schreiben, Bestätigen oder Verschieben von Terminen direkt in der Zeitleiste.
- Vollständiges Audit-Log oder Rekonstruktion früherer Änderungen.
- Automatisch angenommene Beziehungen zwischen Vorhaben oder Kalenderereignissen.
- Produktivdeployment vor der lokalen optischen Abnahme.

**Technische Grundlage:** `backend/app/web/timeline.py` definiert das gemeinsame Darstellungsformat und erzeugt fiktive Beispieldaten ausschließlich im Speicher. Herkunft und Verbindlichkeit können unbekannt sein; Datumswerte, Zeitstempel mit Zeitzone und ungefähre Zeiträume bleiben unterscheidbar. `/ui/zeitleiste` zeigt eine Vorbereitungsmeldung; `?demo=1` ist nur mit `HUGO_TIMELINE_DEMO=true` verfügbar und bleibt hinter der Anmeldung. Die Navigation verwendet eine rein lesende Zählabfrage. Die derzeitige Vorschau ist eine einfache Liste, noch keine Grafik.

**Nächster Schritt für den Agenten:** Auf diesem Darstellungsformat den lokalen optischen Prototyp entwickeln. Anschließend die Vorschau zur Beurteilung bereitstellen, bevor die Datenanbindung umgesetzt wird.
