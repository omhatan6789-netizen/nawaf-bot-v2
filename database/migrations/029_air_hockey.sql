CREATE TABLE IF NOT EXISTS air_hockey_games (
    id UUID PRIMARY KEY,
    player1_id BIGINT NOT NULL,
    player1_name TEXT NOT NULL,
    player2_id BIGINT,
    player2_name TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','playing','finished','cancelled')),
    game_state JSONB NOT NULL,
    winner_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (player2_id IS NULL OR player2_id <> player1_id)
);

CREATE INDEX IF NOT EXISTS air_hockey_games_status_updated_idx
    ON air_hockey_games(status, updated_at DESC);

ALTER TABLE online_game_images
    DROP CONSTRAINT IF EXISTS online_game_images_game_type_check;

ALTER TABLE online_game_images
    ADD CONSTRAINT online_game_images_game_type_check
    CHECK (game_type IN ('connect', 'dots', 'memory', 'word', 'hockey'));
