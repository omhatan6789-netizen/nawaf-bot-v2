CREATE TABLE IF NOT EXISTS online_game_images (
    game_type TEXT PRIMARY KEY CHECK (game_type IN ('connect', 'dots', 'memory')),
    photo_file_id TEXT NOT NULL,
    updated_by BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
