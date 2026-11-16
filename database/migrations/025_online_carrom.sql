ALTER TABLE online_game_lobbies
    DROP CONSTRAINT IF EXISTS online_game_lobbies_game_type_check;
ALTER TABLE online_game_lobbies
    ADD CONSTRAINT online_game_lobbies_game_type_check
    CHECK (game_type IN ('connect','dots','memory','carrom'));
ALTER TABLE online_game_lobbies
    ADD COLUMN IF NOT EXISTS duration_seconds INTEGER NOT NULL DEFAULT 300;

CREATE TABLE IF NOT EXISTS carrom_online_games (
    id UUID PRIMARY KEY,
    lobby_id UUID NOT NULL UNIQUE REFERENCES online_game_lobbies(id) ON DELETE CASCADE,
    players JSONB NOT NULL,
    settings JSONB NOT NULL,
    game_state JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'playing' CHECK (status IN ('playing','finished','cancelled')),
    turn_index INTEGER NOT NULL DEFAULT 0,
    move_no INTEGER NOT NULL DEFAULT 0,
    deadline TIMESTAMPTZ,
    winner_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS carrom_online_games_status_idx
    ON carrom_online_games(status, updated_at DESC);
