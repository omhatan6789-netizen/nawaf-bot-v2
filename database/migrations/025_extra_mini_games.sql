CREATE TABLE IF NOT EXISTS word_games (
 id UUID PRIMARY KEY, owner_id BIGINT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('online','training')),
 status TEXT NOT NULL DEFAULT 'waiting', max_players INTEGER NOT NULL DEFAULT 10,
 word_limit INTEGER NOT NULL DEFAULT 5, win_target INTEGER NOT NULL DEFAULT 5,
 current_index INTEGER NOT NULL DEFAULT 0, words JSONB NOT NULL DEFAULT '[]'::jsonb,
 players JSONB NOT NULL DEFAULT '[]'::jsonb, answers JSONB NOT NULL DEFAULT '{}'::jsonb,
 round_until TIMESTAMPTZ, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS word_games_status_idx ON word_games(status,updated_at DESC);
CREATE TABLE IF NOT EXISTS battleship_games (
 id UUID PRIMARY KEY, mode TEXT NOT NULL CHECK(mode IN ('online','bot')),
 status TEXT NOT NULL DEFAULT 'waiting', difficulty TEXT NOT NULL DEFAULT 'متوسط',
 player1_id BIGINT NOT NULL, player1_name TEXT NOT NULL,
 player2_id BIGINT, player2_name TEXT,
 state JSONB NOT NULL DEFAULT '{}'::jsonb, turn_player_id BIGINT,
 winner_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS battleship_games_status_idx ON battleship_games(status,updated_at DESC);
