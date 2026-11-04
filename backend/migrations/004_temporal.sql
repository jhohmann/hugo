-- Hugo: Zeitliche Planung für Handlungsstränge (Temporal Reasoning)
--
-- event_start / event_end: Wann etwas stattfindet
--   (exakter Zeitpunkt: nur event_start; Zeitraum: beide Felder).
-- deadline (bestehend): harte Frist, nur wenn der Nutzer sie nennt.
-- act_by: Hugos Empfehlung, wann mit der nächsten Aktion oder
--   Vorbereitung begonnen werden sollte.
-- time_precision: 'exact' oder 'approximate' (ungefährer Zeitraum).
-- time_text: ursprüngliche Zeitangabe des Nutzers, wörtlich.

ALTER TABLE threads
    ADD COLUMN IF NOT EXISTS event_start DATE,
    ADD COLUMN IF NOT EXISTS event_end DATE,
    ADD COLUMN IF NOT EXISTS time_precision TEXT
        NOT NULL DEFAULT 'exact'
        CHECK (time_precision IN ('exact', 'approximate')),
    ADD COLUMN IF NOT EXISTS act_by DATE,
    ADD COLUMN IF NOT EXISTS time_text TEXT;

ALTER TABLE threads
    DROP CONSTRAINT IF EXISTS threads_event_range_check;

ALTER TABLE threads
    ADD CONSTRAINT threads_event_range_check
    CHECK (
        event_end IS NULL
        OR (event_start IS NOT NULL AND event_end >= event_start)
    );
