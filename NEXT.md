# Nächste Entwicklungsschritte

Dieses Dokument beschreibt den nächsten geplanten Entwicklungsschritt für Hugo. Es wird nach Umsetzung aktualisiert oder durch ein neues NEXT.md ersetzt.

## Ziel: Vorbereitungsfenster und Blocker-Erkennung

Hugo soll nicht nur Deadlines erkennen, sondern vorausplanen: „Du solltest jetzt mit X anfangen, damit Y rechtzeitig fertig wird."

**Design-Prinzip:** Minimalinvasive Struktur, maximale KI-Freiheit. Keine starren Kanban-Zustände, keine expliziten Abhängigkeiten. Die KI interpretiert den Kontext und entscheidet, was blockiert ist und wann mit der Vorbereitung begonnen werden sollte.

### Aktueller Stand

- Threads haben `act_by`, `event_start`, `event_end`, `time_precision`
- Die Evaluations-Engine erkennt bevorstehende und überfällige Termine
- Keine Vorbereitungsfenster („3 Monate vorher")
- Keine explizite Blocker-Erkennung

### Geplante Änderungen

#### 1. Datenmodell erweitern

Nur zwei neue Felder in `threads`:

| Feld | Typ | Bedeutung |
|---|---|---|
| `blocked_reason` | TEXT, NULL | Warum wartet das? („Visum noch nicht beantragt", „Warte auf Rückmeldung") |
| `preparation_weeks` | INTEGER, NULL | Wie viele Wochen vor `event_start` oder `act_by` sollte begonnen werden |

Migration: `002_thread_preparation.sql`

**Kein** `depends_on_thread_id`, **keine** starren Kanban-Zustände. Die KI erkennt Abhängigkeiten aus dem Kontext.

#### 2. Agentenwerkzeuge erweitern

- `create_thread` und `update_thread` um die neuen Felder ergänzen
- Die KI kann `blocked_reason` setzen und ändern, wenn sie erkennt, dass ein Thread wartet

#### 3. Evaluations-Prompt erweitern

Der Prompt in `evaluation.py` soll zusätzlich prüfen:

- **Vorbereitungsfenster:** „Thread A beginnt in 8 Wochen, `preparation_weeks=12`. Es ist Zeit zu starten."
- **Blocker:** „Thread B hat `blocked_reason='Visum noch nicht beantragt'`. Das Visum sollte jetzt beantragt werden."
- **Kontext-Abhängigkeiten:** „Thread C hängt von Thread D ab (erkennbar aus Beschreibung). Ist D noch offen?"

Beispiel für einen guten Vorschlag:
> „Die Japanreise beginnt in 10 Wochen, `preparation_weeks=12`. Es ist Zeit zu starten. Das Visum ist noch nicht beantragt — das ist der erste Schritt."

#### 4. UI erweitern

- **Thread-Detailansicht:** `blocked_reason` und `preparation_weeks` anzeigen
- **Thread-Liste:** Blockierte Threads mit Grund markieren
- **Heute-Ansicht:** Vorschläge mit Vorbereitungskontext

### Reihenfolge der Umsetzung

1. Migration und Datenmodell
2. Agentenwerkzeuge
3. Evaluations-Prompt
4. UI-Anpassungen
5. Tests

### Erfolgskriterium

Hugo erzeugt Vorschläge wie:
> „Du solltest jetzt mit der Visumsbeantragung beginnen, damit die Flugbuchung rechtzeitig erfolgen kann."

statt nur:
> „Die Japanreise beginnt in 10 Wochen."
