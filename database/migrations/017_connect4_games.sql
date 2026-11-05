CREATE TABLE IF NOT EXISTS connect4_games (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('سهل','متوسط','صعب','مستحيل')),
    board JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'playing' CHECK (status IN ('playing','won','lost','draw')),
    turn_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_move INTEGER,
    winning_cells JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS connect4_games_user_created_idx
    ON connect4_games(user_id, created_at DESC);
