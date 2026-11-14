CREATE TABLE IF NOT EXISTS number_sort_settings (
 id INTEGER PRIMARY KEY CHECK (id=1),
 background_file_id TEXT,
 tile_color TEXT NOT NULL DEFAULT '#7f1d2d' CHECK (tile_color ~ '^#[0-9A-Fa-f]{6}$'),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO number_sort_settings(id) VALUES(1) ON CONFLICT(id) DO NOTHING;

CREATE TABLE IF NOT EXISTS number_sort_rooms (
 id UUID PRIMARY KEY,
 owner_id BIGINT NOT NULL,
 mode TEXT NOT NULL CHECK (mode IN ('online','bot')),
 status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','playing','finished','cancelled')),
 players JSONB NOT NULL DEFAULT '[]'::jsonb,
 settings JSONB NOT NULL DEFAULT '{}'::jsonb,
 state JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS number_sort_rooms_status_idx ON number_sort_rooms(status, updated_at DESC);
