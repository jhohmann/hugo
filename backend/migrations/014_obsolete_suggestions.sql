-- Internal invalidation is auditable and remains distinct from a user rejection.
ALTER TABLE suggestion_reactions ADD COLUMN reason TEXT;
CREATE INDEX idx_suggestion_reactions_suggestion
    ON suggestion_reactions (suggestion_id, id DESC);
