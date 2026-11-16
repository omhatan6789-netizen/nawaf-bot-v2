ALTER TABLE carrom_online_games
    ADD COLUMN IF NOT EXISTS turn_deadline TIMESTAMPTZ;

UPDATE carrom_online_games
SET turn_deadline = NOW() + INTERVAL '20 seconds'
WHERE status = 'playing' AND turn_deadline IS NULL;
