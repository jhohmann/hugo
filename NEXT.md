# NEXT — Hugo als proaktiver persönlicher Assistent

## Ziel und Geltung

Hugo übernimmt die Denkarbeit, aber nicht die Entscheidungshoheit. Der Nutzer kann Ideen und Verpflichtungen mit wenigen Angaben erfassen. Hugo ordnet sie zeitlich ein, beobachtet Entwicklungen und fragt erst nach, wenn fehlende Informationen die Koordination tatsächlich behindern.

Dieser Arbeitsplan übersetzt die Zukunftsvision vom 16.11.2026 in kleine, überprüfbare Entwicklungsaufträge. Schritte 1–4 sind seit dem 17.11.2026 technisch umgesetzt und lokal geprüft. Schritt 5 hat eine geprüfte Bestandsabdeckung; die qualitative Modellabnahme bleibt wie der Zielbetrieb offen. Schritt 6 bietet nun eine geprüfte lokale Bündelung; zusätzliche Zustellkanäle und die betrieblichen Teile von Schritt 7 bleiben offen. [README.md](README.md) bleibt die technische und betriebliche Referenz, [AGENTS.md](AGENTS.md) enthält die Arbeitsregeln. Der bisherige Zeitleistenplan liegt in [GitZeitleiste.md](GitZeitleiste.md) und bleibt erhalten; er ist keine Voraussetzung für proaktive Unterstützung.

„Agenten“ meint hier **Entwicklungsagenten mit abgegrenzten Aufträgen**. Hugo behält einen zentralen modellgeführten Laufzeitagenten mit Werkzeugen. Kein neues Multi-Agenten-System, kein dauerhafter Python-Worker und keine doppelte Modellladung.

**Nutzerfestlegung vom 17.11.2026:** Auf diesem Rechner ist kein Modellzugang
integriert; die Zugänge dürfen als geprüft angenommen werden. Diese Integrations-
prüfung wird für die Weiterentwicklung übernommen und blockiert lokale Pakete nicht.
Das ist von der hier nicht ausgeführten qualitativen Live-Modellbeobachtung zu
unterscheiden. Keine erneute Zugangseinrichtung auf dieser Maschine verlangen.

## Verbindliche Produktentscheidungen

- „Heute“ ist der zentrale Eingang für drei Meldungstypen: **Vorschlag**, **Statusabfrage**, **Rückfrage**. Reine Informationsmeldungen entfallen; jede Meldung ermöglicht eine konkrete Entscheidung oder Handlung.
- Vorschläge bieten Bestätigen, Zurückstellen und Verwerfen. Statusabfragen bieten „Bin dran“, „Pausiert“, „Erledigt“ und „Kein Fortschritt“. Rückfragen bieten zur Frage passende Antworten, einschließlich Freitext, wenn nötig.
- Auch Vorhaben ohne Deadline werden beobachtet. Lange Funkstille bedeutet unbekannten Stand, nicht nachgewiesenen Stillstand und nicht automatisch höhere Priorität.
- Wichtigkeit und aktuelle Handlungsdringlichkeit sind getrennt. Das Modell beurteilt sie anhand belegter Angaben, Abhängigkeiten, Folgen weiteren Wartens, nutzbarer Zeit und früherer Reaktionen. Python erzwingt gültige Zustände und Berechtigungen, keine fachlichen Priorisierungsregeln.
- Beschreibung und gegebenenfalls Deadline reichen zur Erfassung. Aufwand und fachliche Struktur bleiben unbekannt, solange der Nutzer sie nicht nennt. Eine grobe Aufwandsschätzung kann genügen; keine Pflichtabfrage beim Anlegen.
- Hugo erfindet oder erstellt keine Unteraufgaben oder fachlichen Projektschritte. Nutzerseitig genannte Schritte dürfen erfasst werden. Koordinationsvorschläge sind keine bestätigte Projektstruktur.
- Interne Bewertungen und Beobachtung sind autonom erlaubt. Projektabschluss, verbindliche Friständerung und externe Kalenderänderung verlangen eine ausdrückliche Nutzerentscheidung. „Erledigt“ als Antwort ist eine solche Entscheidung; eine angenommene Empfehlung ist kein pauschaler Ausführungsauftrag.
- Keine Meldung ist besser als eine nutzlose Meldung. Maximal drei neue Meldungen pro Tag ist eine **offene Produktoption**, kein beschlossenes Limit. Kritikalität, Bündelung und Hinweismüdigkeit müssen gemeinsam bewertet werden.
- Einmalige Ablehnung oder Zurückstellung ist keine dauerhafte Präferenz. Explizite Hinweispause respektieren; keine Umgehung durch Umformulierung oder einen anderen Meldungstyp.

## Ausgangspunkt im Repository

Stand der Dokumenten- und Quellprüfung am 16.11.2026; keine neue Laufzeitverifikation:

| Bereits vorhanden | Konsequenz für die Umsetzung |
| --- | --- |
| `threads` mit Priorität, `next_action`, Deadline, Ereigniszeitraum, `act_by`, `review_on`, Wartekontext und Vorbereitungswochen | Erweitern statt parallele Projektverwaltung bauen. `preparation_weeks` ist keine Arbeitsaufwandsschätzung. |
| `suggestions` mit offen/bestätigt/zurückgestellt/verworfen, Zustellstatus und Wiedervorlagedatum | Meldungstyp und Antwortsemantik fehlen; Status „bestätigt“ bedeutet aktuell keine externe Ausführung. |
| `thread_events`, Nachrichtenbezüge und Quellen | Historie nutzen, aber weder `updated_at` noch Gesprächszuordnung als Fortschritt oder ausdrückliche Bestätigung interpretieren. |
| Zentraler Tool-Loop in `backend/app/agent/assistant.py` und Auswertung in `backend/app/agent/evaluation.py` | Gemeinsame Anweisungen erweitern. Die Auswertung darf bislang lesen und Vorschläge erzeugen, keine Vorhaben verändern. |
| Exakte Textdeduplizierung, Pausen und Wiedervorlagen | Umformulierungen können erneut erscheinen; frühere bearbeitete Meldungen müssen gezielt in die Bewertung eingehen. |
| Kalender-Lesewerkzeuge und gesonderte Kalenderfreigaben | Verfügbarkeit belegt prüfen; fehlender Kalenderzugriff bedeutet keine freie Zeit. Freigabepfad wiederverwenden. |
| Host-systemd-Timer, authentifizierter Auswertungsendpunkt und gemeinsamer PostgreSQL-Lock | Unbeaufsichtigte Auswertung erhalten; Proxmox, Wiederherstellung und echte Modellqualität gesondert prüfen. |

Eine konkrete Abweichung zur Vision: Der Chatprompt erlaubt derzeit eigenständiges Aktualisieren von `next_action`. Das muss gegenüber fachlichen Projektschritten eingegrenzt werden. Bestehende Werte bleiben erhalten; keine pauschale Löschung oder nachträgliche Umdeutung.

## Arbeitsweise mit Entwicklungsagenten

Ein integrierender Agent verantwortet jeweils einen vertikalen Schritt von Persistenz bis Oberfläche. Bei sinnvoller Trennung kann ein zweiter Agent unabhängig Tests und Grenzfälle prüfen. Datenvertrag, Migrationen und gemeinsam genutzte Dateien werden zuerst abgestimmt; keine parallelen konkurrierenden Änderungen daran. Die folgenden Pakete sind Aufträge, keine dauerhaft getrennten Agentenrollen.

Jeder Auftrag beginnt mit aktueller Quellprüfung und endet mit Code, passenden Tests, README-Anpassung und kurzem Nachweis: Was funktioniert, was wurde nur simuliert, was bleibt offen? Status hier erst nach nachgewiesener Abnahme ändern. Neue nummerierte Migrationen ergänzen, bestehende nicht bearbeiten; Daten und bestehende APIs erhalten. Vor jedem Paket Arbeitsbaum und aktuelle Migrationsnummer prüfen.

## Umsetzung in Reihenfolge

### 1. Entscheidungsgrenzen absichern

**Stand 17.11.2026:** Gemeinsame Anweisungen, technische Agentensperre für Abschluss/
Archivierung und bestehende Friständerungen sowie direkte Nutzeraktionen in der
Vorhabenansicht umgesetzt. Veraltete Formulare werden unter Zeilensperre abgewiesen;
Migration 009 unterscheidet `user_decision` im Ereignisprotokoll. Auch ein expliziter
Chatauftrag führt vorerst zum Nutzerentscheid in dieser Ansicht, nicht zu einer
vom Modell behaupteten Freigabe. Erstmalige Fristen und fachlicher Inhalt bleiben
modellgeführt. Keine Bestandsdaten gelöscht oder migriert.

**Prüfstand:** Im ersten Lauf 164 Tests bestanden und 29 Datenbanktests übersprungen.
Die anschließende isolierte PostgreSQL-18-Prüfung bestand 43 Datenbank-/Migrations-
und Wiedervorlagetests; zwei Chromium-Proben für Desktop/Smartphone bestanden ebenfalls.
Echtes Modellverhalten und Proxmox bleiben offen; Details und Prüfgrenzen in
[README.md](README.md#entscheidungsgrenzen-am-17112026). Schritt 1 ist technisch
geprüft, noch nicht vollständig produktseitig abgenommen. Die fehlende externe
Modellprüfung verhindert die unabhängige lokale Umsetzung der nächsten technischen
Pakete nicht; sie bleibt vor breiter Nutzung nachzuholen.

**Agentenauftrag:** Die neue Autonomiegrenze im Chat und bei der Auswertung konsistent machen, bevor neue Schreibmöglichkeiten hinzukommen.

- Gemeinsame Anweisungen zu Unteraufgaben, Unsicherheit, minimaler Erfassung und bedarfsabhängigen Rückfragen anpassen.
- `next_action` auf vom Nutzer gelieferte fachliche Schritte beziehungsweise klar erkennbare Koordination begrenzen; Empfehlungen nicht als zugesagte Arbeitsschritte speichern.
- Für Abschluss und Änderung harter Fristen einen nachvollziehbaren Nutzerauftrag verlangen. Ein vom Modell gelieferter Wahrheitswert „bestätigt“ genügt nicht als Berechtigungsnachweis. Bestehende Schreibpfade prüfen und bei Bedarf einen eng begrenzten, serverseitig belegten Entscheidungsweg ergänzen.
- Bestehende Vorschlagsbestätigung und Kalenderfreigabe ausdrücklich auseinanderhalten.

**Dateien:** `backend/app/agent/assistant.py`, `backend/app/agent/evaluation.py`, `backend/app/chat_service.py`, `backend/app/storage/threads.py`; Tests in `tests/test_thread_tools.py`, `tests/test_evaluation.py` und gegebenenfalls `tests/test_chat_context.py`.

**Abnahme:** „Ich überlege, das Haus zu modernisieren“ erzeugt weder erfundene Arbeitsschritte noch Pflichtfragen. Eine automatische Bewertung kann das Projekt nicht abschließen oder seine harte Frist verschieben. Ein ausdrücklicher Nutzerauftrag bleibt ausführbar. Werkzeugtests belegen die technische Grenze; echte Modellproben müssen die Gesprächsqualität separat zeigen.

### 2. Typisierte Meldungen durchgängig in „Heute“

**Stand 17.11.2026:** Migration 010, drei Meldungstypen, typabhängige UI-/API-Antworten,
unveränderliche Antwortbelege und zugeordnete Frage-/Antwortgespräche umgesetzt.
Doppelte Antworten sind idempotent; abweichende oder veraltete Antworten werden
abgewiesen. „Erledigt“ und seine Antwort werden gemeinsam mit dem Vorhabenabschluss
transaktional gespeichert. Legacy-Vorschläge bleiben nutzbar. Technische Tests und
Desktop-/Smartphone-Proben bestanden; echte Modellwahl der Meldungstypen bleibt offen.

**Abhängigkeit:** Schritt 1.

**Agentenauftrag:** Einen vollständigen Weg von `create_suggestion` bis zu drei unterscheidbaren Karten mit passenden Aktionen umsetzen.

- `suggestions` kompatibel um einen Meldungstyp erweitern. Bestehende Einträge als Vorschläge erhalten; alte API-Aufrufe ohne Typ bleiben gültig.
- Typabhängige Antwortverträge serverseitig validieren: feste Statusantworten, begrenzte Auswahl bei Rückfragen und bei Bedarf Freitext. Modellgenerierte Beschriftungen dürfen keine beliebigen Aktionen oder ausführbaren Nutzdaten definieren.
- Antworten mit Meldungsbezug, Zeitpunkt und Herkunft dauerhaft erfassen. Übermittlung muss bei Doppelklick/Wiederholung idempotent sein; veraltete oder bereits beantwortete Karten dürfen keine zweite Zustandsänderung auslösen.
- Vorschläge bestätigen, zurückstellen und verwerfen; Statusantworten und Rückfragen zunächst eindeutig als Nutzerangabe speichern. Semantische Fortschrittsfelder folgen in Schritt 3. „Erledigt“ darf nur das eindeutig zugeordnete Vorhaben mit ausdrücklicher Entscheidung abschließen.
- Freitextantworten dem richtigen Vorhaben und Fragekontext zuführen. Kein allgemeines „Bestätigen“ unter einer Frage.

**Dateien:** neue Migration unter `backend/migrations/`, `backend/app/storage/suggestions.py`, `backend/app/agent/evaluation.py`, `backend/app/agent/assistant.py`, `backend/app/main.py`, `backend/app/web/routes.py`, `backend/app/web/templates/heute.html`; Tests in `tests/test_suggestions.py`, `tests/test_web.py`, `tests/test_evaluation.py` und `tests/test_migrations.py`.

**Abnahme:** Alle drei Typen können erzeugt, angezeigt und korrekt beantwortet werden. Ungültige Typ-/Antwortkombinationen werden abgewiesen. Altbestand, Authentifizierung, Origin-Schutz, Escaping und Wiedervorlage bleiben intakt. Desktop und Smartphone im Browser prüfen. Kein Klick auf „Vorschlag bestätigen“ verändert automatisch den Kalender.

### 3. Fortschritt, Bestätigung und Pausen belastbar unterscheiden

**Stand 17.11.2026:** Migration 011 ergänzt Projektpause, belegten Fortschrittstag,
Erfassungszeit, letzte Statusbestätigung und letzte Antwort. Letzte Meldungserstellung
wird separat abgeleitet. Keine historischen Fortschrittswerte erfunden. Statusantworten
setzen keinen Fortschritt. Projektpause ist orthogonal zum Wartestatus; Wiederaufnahme
erfolgt ausdrücklich durch den Nutzer. Gezielte Datenbank-/Werkzeug-/Webtests bestanden.
Frage-/Antwortbelege sind mit einem lesenden Werkzeug im Chat und in der Auswertung
abrufbar; Fortschritt schreibt ausschließlich der Chat mit belegter Nutzernachricht.
Echte Modellinterpretation und Alltagsergebnisse bleiben offen.

**Abhängigkeit:** Schritt 2.

**Agentenauftrag:** Nutzerangaben so persistieren und im Bewertungskontext bereitstellen, dass Hugo fehlenden Stand erkennt.

- Getrennt erfassen: letzter belegter Fortschritt, letzte ausdrückliche Bestätigung des Stands, letzte Nutzerreaktion und letzter Hinweis. Fachlicher Zeitpunkt und Erfassungszeitpunkt unterscheiden; unbekannte Werte bleiben leer.
- „Bin dran“ bestätigt den aktuellen Stand, behauptet aber keinen konkreten Fortschritt. „Kein Fortschritt“ ist eine neue Information ohne Fortschrittsdatum. „Pausiert“ wird ausdrücklich erfasst und unterdrückt passende Hinweise; kein erfundenes Wiederaufnahmedatum.
- Vor Umsetzung entscheiden, ob Pause ein eigener Zustand oder eine orthogonale Eigenschaft ist. `waiting`, Projektpause und bloße Hinweispause nicht gleichsetzen; laufende Verpflichtungen anderer Vorhaben weiter berücksichtigen.
- Vorhandenes Ereignisprotokoll und Antwortbelege nutzen. Notwendige neue Felder mit klarer Semantik ergänzen, keine rückwirkenden Fortschrittsdaten aus Änderungszeitstempeln ableiten.
- Der Auswertung nur ein eng begrenztes Werkzeug für interne Bewertungen geben, falls deren Persistenz nötig ist. Daraus keine allgemeinen Schreibrechte für Fristen, Abschluss oder fachliche Struktur machen.

**Dateien:** `backend/app/storage/threads.py`, `backend/app/storage/thread_events.py`, `backend/app/storage/suggestions.py`, `backend/app/agent/assistant.py`, `backend/app/agent/evaluation.py`, Vorhabendetail und neue Migration; Tests in `tests/test_thread_events.py`, `tests/test_follow_up.py`, `tests/test_thread_storage.py` und `tests/test_migrations.py`.

**Abnahme:** Ein Hugo-Hinweis setzt keinen Nutzerfortschritt. Nach längerer Funkstille bleibt der Fortschritt unbekannt. Alle vier Statusantworten haben unterscheidbare, auditierbare Folgen; eine explizite Pause bleibt bei wiederholten Auswertungen wirksam. Historischer Altbestand bleibt nutzbar und wird nicht mit erfundenen Bestätigungen aufgefüllt.

### 4. Reaktionen berücksichtigen und Wiederholungen verhindern

**Stand 17.11.2026:** Migration 012 speichert ausdrückliche Statusreaktionen,
das lesende Werkzeug und der Auswertungskontext enthalten jüngste Reaktionen samt
ursprünglichem Anlass. Ein stabiler `occasion_key` verhindert umformulierte Duplikate
über Läufe und Meldungstypen; parallele allgemeine Neuanlagen sind transaktional
abgesichert. Migration 014 und ein eng begrenztes Werkzeug ermöglichen zudem die
begründete Aufhebung konkret überholter offener/vertagter Karten, ohne beantwortete
Nutzerentscheidungen umzuschreiben. Gezielte Datenbank-/Werkzeug-/Webprüfungen bestanden. Die semantische
Wahl des Schlüssels, ein tatsächlich neuer Anlass und das Erkennen dauerhafter
Präferenzen bleiben modellgeführt; dafür liegt noch kein echter Modellnachweis vor.
Keine Präferenz wird pauschal aus einer einzelnen Ablehnung gespeichert.

**Abhängigkeit:** Schritte 2–3; vor einer Ausweitung der Hinweiserzeugung.

**Agentenauftrag:** Die bestehende Textdeduplizierung durch belegbaren Anlass- und Reaktionskontext ergänzen.

- Jüngste beantwortete, verworfene und zurückgestellte Meldungen samt Grund gezielt abrufbar machen; keine unbegrenzte Historie in jeden Prompt laden.
- Modell soll denselben Anlass auch bei anderer Formulierung erkennen. Technische Identität und transaktionale Prüfung schützen zusätzlich gegen doppelte Einreichungen. Semantische Ähnlichkeit allein darf weder Meldungen zusammenführen noch einen alten Datensatz überschreiben.
- Ein erneuter Hinweis benötigt eine benennbare Änderung, einen neuen entscheidungsrelevanten Anlass oder eine ausdrücklich fällige Wiedervorlage. Neue Reaktion oder Vorhabenänderung macht alte Fragen gegebenenfalls gegenstandslos.
- Dauerhafte Präferenzen nur aus belastbaren Mustern oder ausdrücklicher Aussage ableiten, mit Belegen, Korrekturmöglichkeit und begrenztem Geltungsbereich. Keine starre „nach drei Ablehnungen“-Regel.

**Dateien:** `backend/app/storage/suggestions.py`, `backend/app/agent/evaluation.py`, gegebenenfalls bestehende Memory-Werkzeuge; Tests in `tests/test_suggestions.py`, `tests/test_follow_up.py` und `tests/test_evaluation.py`.

**Abnahme:** Wiederholte identische Läufe produzieren keine umformulierten Duplikate. Zurückstellen gilt typenübergreifend. Eine einmalige Ablehnung wird nicht zur dauerhaften Präferenz. Ein tatsächlich neuer Anlass bleibt zulässig; begründen, weshalb er neu ist. Neben technischen Tests feste Modellfälle wiederholt prüfen.

### 5. Modellgeführte Koordination auch ohne Deadline

**Stand 17.11.2026:** Der technische Kontext umfasst Beobachtungsdaten und Reaktionen;
Aufwand und fachliche Abhängigkeiten bleiben als belegte Angaben im Frage-/Antwort-
beziehungsweise Vorhabenkontext zugänglich. Keine Schätzwerte oder Unteraufgaben aus
fehlenden Angaben erzeugt. Migration 013 ergänzt eine erfolgreiche, fortlaufende
Bestandsabdeckung: bis zu 50 bisher vordringliche Vorhaben plus bis zu 50 aus einem
ID-Zyklus, mit sichtbarer Abdeckungsmetadaten und lesendem Seitenwerkzeug. 123 Vorhaben
wurden im Datenbanktest über drei Läufe vollständig berücksichtigt; Fehlversuche
verschieben den Cursor nicht. Die qualitative Szenarioabnahme mit echtem Modell
steht aus. Dafür gibt es `scripts/check_proactive_planning.py` mit synthetischen Fällen;
Dry-Run verursacht keinen Modellaufruf und ist kein Qualitätsnachweis.

**Abhängigkeit:** Schritte 3–4.

**Agentenauftrag:** Den bestehenden Auswertungskontext um Fortschritt, Reaktionen und Planungsunsicherheit erweitern; Wichtigkeit von heutiger Dringlichkeit trennen.

- Auch ruhende, undatierte Vorhaben berücksichtigen. Die bisherige Startauswahl von bis zu 50 offenen Vorhaben auf systematische Auslassungen prüfen und eine begrenzte, nachvollziehbare Abdeckung größerer Bestände ermöglichen.
- Aufwandsschätzung, relevante Abhängigkeiten und deren Herkunft nur soweit nötig strukturiert zugänglich machen. Nutzerangabe, Modellbewertung und Unbekanntes unterscheidbar halten; keine automatische Zerlegung in Unteraufgaben.
- Kalender und andere Verpflichtungen im relevanten Zeitraum lesen. Freie Kalenderlücken sind nicht automatisch nutzbare Arbeitszeit; Aufwand, Arbeitsfenster und persönliche Angaben berücksichtigen, fehlende Daten offenlassen.
- Rückfrage nur, wenn ihre Antwort eine aktuelle Koordinationsentscheidung verändert. Sonst mit Unsicherheit weiterarbeiten oder bewusst keine Meldung erzeugen.
- Bewertung begründet einen Vorschlag, eine Statusabfrage, eine Rückfrage oder Stille. Keine feste gewichtete Punkteformel und keine domänenspezifischen Warnregeln einführen.

**Dateien:** `backend/app/agent/evaluation.py`, gemeinsame Planungsanweisungen in `backend/app/agent/assistant.py`, bestehende Thread-Speicherung und Kalender-Lesewerkzeuge; Tests in `tests/test_evaluation.py`, `tests/test_calendar_search.py` und `tests/test_thread_tools.py`.

**Abnahmefälle:**

| Fall | Erwartetes Verhalten |
| --- | --- |
| Deadline noch weit weg, nutzbare Zeit schrumpft | Rechtzeitiger konkreter Hinweis, wenn belegbar; kein pauschaler Vorlauf. |
| Seit Wochen keine Nachricht zu einem wichtigen undatierten Vorhaben | Nützliche Statusabfrage möglich, keine Behauptung von Stillstand. |
| Langfristig wichtig, aktuell bewusst pausiert | Keine tägliche Hochstufung oder erneute Rückfrage. |
| Aufwand unbekannt, ohne ihn keine belastbare Entscheidung möglich | Gezielte Rückfrage nach grober Schätzung, keine erfundenen Teilaufgaben. |
| Kalenderzugriff fehlgeschlagen | Kapazität bleibt ungeprüft; kein angeblich freier Samstag. |
| Viele offene Vorhaben, eines außerhalb der ersten 50 | Über mehrere Läufe nachvollziehbar berücksichtigt, nicht dauerhaft vergessen. |
| Keine relevante Änderung oder Gelegenheit | Keine neue Meldung. |

### 6. „Heute“ bündeln und Benachrichtigungen vorbereiten

**Stand 17.11.2026:** Lokale Bündelung umgesetzt: Meldungen je Vorhaben zusammen,
allgemeine Karten unabhängig, Sortierung nach bestehender Meldungspriorität und
empfohlenem Datum. Zehn Gruppen pro Seite, getrennte Seiten für offene/vertagte
Karten, Gesamtzähler ohne bisherige Abschneidung und Rücksprung nach Aktionen.
Nur Karten der offenen angezeigten Seite werden als zugestellt markiert; keine
Nutzerantwort oder Fortschrittsannahme daraus. Ohne zusätzliche Migration oder
Modellaufrufe. 420 Tests und sechs Browserproben bestanden, darunter echte app.dev-
Prüfungen von Seite 2 und ihrer Antwortverarbeitung; mobile Darstellung gesichtet.
Ein Tagesbudget bleibt unbeschlossen, weitere Zustellkanäle sind nicht angebunden.

**Abhängigkeit:** Schritt 5 und brauchbare Ergebnisse aus Schritt 7.

**Agentenauftrag:** Die nutzbaren Meldungen priorisiert und ruhig präsentieren. Erst danach einen zusätzlichen Zustellkanal entwerfen.

- Tagesübersicht aus bestehenden handlungsfähigen Karten bilden; keine zweite konkurrierende Vorschlagsliste und keine obligatorische Tageszusammenfassung.
- Bündelung und Auswahl nach Relevanz prüfen. Ein mögliches Tagesbudget als bewertbare Produktoption behandeln; kritische Hinweise und deren begründete Ausnahme sichtbar nachvollziehbar machen. Bestehende offene Meldungen nicht durch ein Limit unsichtbar verlieren.
- Zustellung, Sichtbarkeit und Nutzerentscheidung getrennt halten. Öffnen einer Seite ist keine Antwort und kein Fortschritt.
- Push-Kanal erst separat auswählen und technisch freigeben: Einwilligung, Ruhezeiten, sensible Vorschautexte, Wiederholungs- und Fehlerverhalten. Keine neue Mailintegration aus diesem Plan ableiten.
- Spontane Meldungen benötigen einen passenden zusätzlichen Auslöser oder häufigere begrenzte Prüfungen; der bisher tägliche Timer garantiert keine sofortige Reaktion. Keine neue dauerhafte Worker-Architektur voraussetzen.

**Abnahme:** „Heute“ bleibt auch ohne neue Meldung sinnvoll und ohne Verwaltungszwang nutzbar. Ein Kanalfehler erzeugt keine doppelten Meldungen; eine Push-Nachricht gilt nicht als Bestätigung. Benachrichtigungen sind ein eigener späterer Auftrag, nicht Bestandteil der ersten Ausbaustufe.

### 7. Reale Proaktivität und Betrieb nachweisen

**Teilnachweis 17.11.2026:** Vollständiger Stand bis Migration 014: 411 Tests
bestanden, 14 optionale Prüfungen übersprungen; sechs separat aktivierte Chromium-
Proben bestanden, davon zwei mit echtem app.dev-Start, Anmeldung und PostgreSQL. Lokaler Backup-/Restore-Test unter PostgreSQL 18 erfolgreich:
22 Tabellen samt Inhalten und Sequenzen sowie 13 Migrationsprüfsummen erhalten;
synthetische Antwort, Pause und unbekannter Fortschritt ebenfalls. Keine bestehenden
Anwendungsdatenbanken oder Volumes berührt. Diese Probe ersetzt weder den Docker-/
PostgreSQL-17- noch den Proxmox-Nachweis. Anschließend bestanden 77 gezielte
Regressionen für konsistente Antwortwiederholung und Aufhebungsbegründung.
Echte Modellabnahme bleibt mangels Zugang offen.

**Beginn:** Kleine feste Prüffälle ab Schritt 1; integrierte Alltagsprüfung nach Schritt 5. Kein abschließendes Sammelprojekt, das Tests bis zum Ende aufschiebt.

**Agentenauftrag:** Technische Sicherheit und tatsächliche Entlastung getrennt nachweisen.

- Szenarien mit kontrollierter Zeit, Nutzerreaktionen und belegtem Kontext als Regressionen pflegen. Tageswechsel, Europe/Berlin und Sommerzeit berücksichtigen. Sicherheits- und Persistenzfälle deterministisch testen; Modellqualität durch wiederholte begrenzte echte Modellproben beurteilen.
- Manuelle Diagnose unter `scripts/` mit synthetischen Daten, klarer Kostenbegrenzung und ohne Ausführung beim Import. Keine echten Kalenderänderungen oder künstlichen Verpflichtungen erzeugen.
- Im Proxmox-LXC den Host-Timer, Authentifizierung, gemeinsamen PostgreSQL-Lock bei parallelen manuellen/geplanten Aufrufen, Fehlererholung, Update und Backup/Restore in isolierter Zielumgebung prüfen. PSS-Messung zur Worker-Ablösung bleibt offen, bis sie dort durchgeführt wurde.
- Im Alltag relevante Hinweise, Wiederholungen, unnötige Fragen, übersehene Handlungsfenster, nötige Nutzerkorrekturen und Tokenverbrauch beobachten. Weniger Meldungen allein ist kein Erfolg: hilfreiche Interventionen dürfen nicht fehlen.
- Kriterien für einen begrenzten Beobachtungszeitraum vor dessen Beginn festlegen. Nutzerfeedback zur tatsächlichen Entlastung hat Vorrang vor erzeugter Meldungszahl.

**Abnahme:** Ein geplanter Lauf ohne Chatnachricht erzeugt einen belegbar hilfreichen Hinweis oder bleibt begründet still. Auf Antwort, Pause und geänderten Kontext reagiert der nächste Lauf richtig. README dokumentiert Datum, Umgebung, reale/simulierte Dienste, Ergebnisse und offene Grenzen. Mocktests werden nicht als Beleg für Modellqualität, Google-Verhalten oder Proxmox-Betrieb ausgegeben.

## Reihenfolge und nächster konkreter Auftrag

**Hauptpfad:** 1 → 2 → 3 → 4 → 5 → 6. Schritt 7 begleitet alle Schritte und ist die Freigabeschwelle für breitere Zustellung. Betriebskontrollen ohne Codeänderungen können unabhängig vorbereitet werden. Die Zeitleiste bleibt ein eigener, nachgeordneter Auftrag gemäß [GitZeitleiste.md](GitZeitleiste.md).

**Als Nächstes:** Die lokale Bündelung im Alltag mit den vorhandenen geprüften
Zugängen beobachten: hilfreiche Interventionen, unnötige Wiederholungen, überholte
Fragen und Korrekturbedarf. Bei verfügbarer Laufzeitumgebung können die fünf
synthetischen Fälle gezielt mit `scripts/check_proactive_planning.py --case <Fall>`
geprüft werden; fehlender Modellzugang auf diesem Rechner blockiert keine weitere
lokale Entwicklung. Zusätzlichen Zustellkanal erst als eigenen Auftrag auswählen
und dessen Einwilligung, Ruhezeiten und Fehlerverhalten umsetzen. Zielbetrieb,
Host-Timer, PSS und PostgreSQL 17 separat verifizieren, ohne sie aus lokalen Tests
abzuleiten. Letzter Stand: 420 Regressionen und sechs Browserproben bestanden,
Restore-Probe bis Migration 013 erledigt. Keine Unteraufgabenverwaltung vorziehen.
