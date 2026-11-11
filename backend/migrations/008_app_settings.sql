CREATE TABLE app_settings (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    values JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(values) = 'object'),
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO app_settings (id) VALUES (1);
