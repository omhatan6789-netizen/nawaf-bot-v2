CREATE TABLE IF NOT EXISTS quick_game_rooms (
 id UUID PRIMARY KEY,
 game_type TEXT NOT NULL CHECK (game_type IN ('cups','timer')),
 owner_id BIGINT NOT NULL,
 owner_name TEXT NOT NULL,
 mode TEXT NOT NULL DEFAULT 'online' CHECK (mode IN ('online','bot')),
 status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','playing','finished')),
 players JSONB NOT NULL DEFAULT '[]'::jsonb,
 settings JSONB NOT NULL DEFAULT '{}'::jsonb,
 state JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS quick_game_rooms_status_updated_idx ON quick_game_rooms(status, updated_at DESC);
