-- Unknown historical progress remains NULL. A project pause is not a waiting state.
ALTER TABLE threads
    ADD COLUMN paused BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN last_progress_on DATE,
    ADD COLUMN progress_recorded_at TIMESTAMPTZ,
    ADD COLUMN last_confirmed_at TIMESTAMPTZ,
    ADD COLUMN last_response_at TIMESTAMPTZ;
