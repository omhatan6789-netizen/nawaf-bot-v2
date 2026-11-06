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
