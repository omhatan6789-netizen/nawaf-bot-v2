CREATE TABLE IF NOT EXISTS mini_app_sounds (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    file_id TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'audio/mpeg',
    media_kind TEXT NOT NULL CHECK (media_kind IN ('audio', 'video')),
    file_size BIGINT NOT NULL DEFAULT 0,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mini_app_sounds_created_at
    ON mini_app_sounds (created_at DESC);