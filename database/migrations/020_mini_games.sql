CREATE TABLE IF NOT EXISTS mini_game_challenges (
    id UUID PRIMARY KEY,
    game_type TEXT NOT NULL CHECK (game_type IN ('dots','memory')),
    chat_id BIGINT NOT NULL,
    player1_id BIGINT NOT NULL,
    player1_name TEXT NOT NULL,
    player2_id BIGINT NOT NULL,
    player2_name TEXT NOT NULL,
    wager BIGINT NOT NULL CHECK (wager > 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','choosing','playing','won','draw','declined','cancelled')),
    player1_choice TEXT,
    player2_choice TEXT,
    rps_result TEXT,
    turn_player_id BIGINT,
    turn_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    game_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    winner_id BIGINT,
    wager_settled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (player1_id <> player2_id)
);
CREATE INDEX IF NOT EXISTS mini_game_challenges_players_idx
    ON mini_game_challenges(player1_id, player2_id, created_at DESC);
