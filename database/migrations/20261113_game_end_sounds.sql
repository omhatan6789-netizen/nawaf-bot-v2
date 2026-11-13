CREATE TABLE IF NOT EXISTS game_end_sounds (
    scope_key TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    mime_type TEXT,
    media_kind TEXT NOT NULL DEFAULT 'audio',
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
