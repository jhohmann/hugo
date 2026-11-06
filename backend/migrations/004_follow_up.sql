-- Review dates are internal planning dates, not deadlines or calendar events.
ALTER TABLE threads
    ADD COLUMN review_on DATE,
    ADD COLUMN waiting_for TEXT;

ALTER TABLE suggestions ADD COLUMN deferred_until DATE;
ALTER TABLE suggestions ADD CONSTRAINT suggestions_deferral_status_check
    CHECK (deferred_until IS NULL OR status = 'deferred');

CREATE INDEX idx_threads_review ON threads(review_on)
    WHERE status NOT IN ('completed', 'archived');
CREATE INDEX idx_suggestions_deferred ON suggestions(deferred_until)
    WHERE status = 'deferred';
