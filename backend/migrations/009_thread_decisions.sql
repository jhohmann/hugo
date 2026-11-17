-- Explicit UI decisions are distinguishable from model-led conversation updates.
ALTER TABLE thread_events DROP CONSTRAINT thread_events_origin_check;
ALTER TABLE thread_events ADD CONSTRAINT thread_events_origin_check
    CHECK (origin IN ('conversation', 'internal', 'user_decision'));
