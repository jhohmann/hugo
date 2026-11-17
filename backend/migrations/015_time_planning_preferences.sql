-- User-specified planning preferences, editable in Settings. Preserve other values
-- and any rules already configured before this migration.
UPDATE app_settings
SET values = values || jsonb_build_object('HUGO_PLANNING_RULES', $rules$
Zeitzone: Europe/Berlin.
Arbeit: Im Kalender „julianhohmann“ stehen meine Arbeitstermine. Dieser Kalender ist für Arbeitsvorhaben relevant. Kernzeit ist Montag bis Freitag von 08:00 bis 16:30 Uhr. Arbeit außerhalb dieser Kernzeit nicht als reguläre Kapazität voraussetzen. Wochenendarbeit braucht eine dringende, konkret erläuterte Begründung; sie ist keine automatische Ausweichmöglichkeit.
Privat: Private Vorhaben gehören in die übrige Zeit außerhalb der Kernzeit. Dafür sind die Kalender „julianhohmann@googlemail“ und „gemeinsame Termine“ relevant. Die übrige Zeit ist nicht automatisch vollständig nutzbar; keine Schlaf-, Erholungs- oder sonstigen Verfügbarkeitszeiten erfinden.
Sperrzeiten: Einträge im Kalender „Urlaube“ sperren ihren gesamten Zeitraum für neue Termine, sowohl beruflich als auch privat, auch wenn sie im Kalender als verfügbar markiert sind. Ganztägige Einträge sperren die jeweiligen ganzen Tage.
Optionale Veranstaltungen: „Jahrestermine“ enthält interessante Veranstaltungen, die man ins Auge fassen könnte. Diese sind keine Zusagen und blockieren keine Zeit. Bei passendem Anlass darf Hugo eine konkrete Veranstaltung vorschlagen; eine Teilnahme nicht voraussetzen.
Andere Unterkalender nicht pauschal als Belegung verwenden. Bereits bekannte verbindliche Zusagen und konkrete bereichsübergreifende Konflikte trotzdem berücksichtigen. Kalendernamen über die tatsächliche Kalenderliste zuordnen; bei unklarer Zuordnung keine IDs raten und keine freie Zeit behaupten.
$rules$),
    revision = revision + 1,
    updated_at = NOW()
WHERE id = 1 AND NOT (values ? 'HUGO_PLANNING_RULES');
