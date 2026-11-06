CREATE TABLE IF NOT EXISTS mini_game_solo (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    game_type TEXT NOT NULL CHECK (game_type IN ('dots','memory')),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('سهل','متوسط','صعب','مستحيل')),
    status TEXT NOT NULL DEFAULT 'playing' CHECK (status IN ('playing','won','lost','draw')),
    turn_player_id BIGINT NOT NULL,
    turn_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    game_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS mini_game_solo_user_idx
    ON mini_game_solo(user_id, created_at DESC);
