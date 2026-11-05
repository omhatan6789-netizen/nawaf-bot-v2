CREATE TABLE IF NOT EXISTS chess_games (
    id TEXT PRIMARY KEY,
    game_type TEXT NOT NULL CHECK (game_type IN ('ai','pvp')),
    status TEXT NOT NULL CHECK (status IN ('waiting','active','finished','cancelled')),
    group_id BIGINT,
    white_user_id BIGINT NOT NULL,
    black_user_id BIGINT,
    white_name TEXT NOT NULL,
    black_name TEXT NOT NULL,
    bot_name TEXT,
    difficulty TEXT,
    time_control_seconds INTEGER NOT NULL DEFAULT 0,
    white_time_ms BIGINT NOT NULL DEFAULT 0,
    black_time_ms BIGINT NOT NULL DEFAULT 0,
    clock_started_at TIMESTAMPTZ,
    fen TEXT NOT NULL,
    moves JSONB NOT NULL DEFAULT '[]'::jsonb,
    stake_each BIGINT NOT NULL DEFAULT 0,
    settled BOOLEAN NOT NULL DEFAULT FALSE,
    winner_user_id BIGINT,
    result TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS chess_games_players_idx
    ON chess_games (white_user_id, black_user_id, status);
CREATE INDEX IF NOT EXISTS chess_games_group_idx
    ON chess_games (group_id, status);
