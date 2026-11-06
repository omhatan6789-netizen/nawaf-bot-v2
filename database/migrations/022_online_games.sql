CREATE TABLE IF NOT EXISTS online_game_lobbies (
    id UUID PRIMARY KEY,
    game_type TEXT NOT NULL CHECK (game_type IN ('connect','dots','memory')),
    creator_id BIGINT NOT NULL,
    creator_name TEXT NOT NULL,
    player2_id BIGINT,
    player2_name TEXT,
    chat_id BIGINT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','starting','playing','finished','cancelled')),
    game_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (player2_id IS NULL OR player2_id <> creator_id)
);
CREATE INDEX IF NOT EXISTS online_game_lobbies_status_created_idx
    ON online_game_lobbies(status, created_at DESC);
