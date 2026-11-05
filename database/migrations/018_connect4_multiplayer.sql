ALTER TABLE connect4_games
    ADD COLUMN IF NOT EXISTS game_mode TEXT NOT NULL DEFAULT 'bot',
    ADD COLUMN IF NOT EXISTS chat_id BIGINT,
    ADD COLUMN IF NOT EXISTS player2_id BIGINT,
    ADD COLUMN IF NOT EXISTS player1_name TEXT,
    ADD COLUMN IF NOT EXISTS player2_name TEXT,
    ADD COLUMN IF NOT EXISTS turn_player_id BIGINT,
    ADD COLUMN IF NOT EXISTS winner_id BIGINT,
    ADD COLUMN IF NOT EXISTS wager BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bot_id BIGINT,
    ADD COLUMN IF NOT EXISTS bot_name TEXT NOT NULL DEFAULT 'البوت',
    ADD COLUMN IF NOT EXISTS bot_move_pending BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS wager_settled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS connect4_games_player2_idx
    ON connect4_games(player2_id, created_at DESC);

CREATE TABLE IF NOT EXISTS connect4_challenges (
    id UUID PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT,
    challenger_id BIGINT NOT NULL,
    challenger_name TEXT NOT NULL,
    opponent_id BIGINT NOT NULL,
    opponent_name TEXT NOT NULL,
    wager BIGINT NOT NULL CHECK (wager > 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','choosing','playing','declined','cancelled')),
    challenger_choice TEXT,
    opponent_choice TEXT,
    rps_message_id BIGINT,
    game_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS connect4_challenges_chat_idx
    ON connect4_challenges(chat_id, created_at DESC);
