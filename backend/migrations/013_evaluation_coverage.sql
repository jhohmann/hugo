-- Continue a bounded review cycle only after a successful evaluation.
ALTER TABLE evaluation_runs
    ADD COLUMN review_cursor BIGINT NOT NULL DEFAULT 0 CHECK (review_cursor >= 0);
