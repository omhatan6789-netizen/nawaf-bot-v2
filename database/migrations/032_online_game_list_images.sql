CREATE TABLE IF NOT EXISTS online_game_list_images (
    game_type TEXT PRIMARY KEY,
    photo_file_id TEXT NOT NULL,
    updated_by BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
