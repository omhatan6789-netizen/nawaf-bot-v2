CREATE TABLE IF NOT EXISTS game_player_results (
    id BIGSERIAL PRIMARY KEY,
    game_key TEXT NOT NULL,
    game_type TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    player_name TEXT NOT NULL DEFAULT 'لاعب',
    result TEXT NOT NULL CHECK (result IN ('win', 'loss')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (game_key, user_id)
);
CREATE INDEX IF NOT EXISTS game_player_results_result_created_idx
    ON game_player_results (result, created_at DESC);
CREATE INDEX IF NOT EXISTS game_player_results_user_idx
    ON game_player_results (user_id, result);
