ALTER TABLE online_game_images
    DROP CONSTRAINT IF EXISTS online_game_images_game_type_check;

ALTER TABLE online_game_images
    ADD CONSTRAINT online_game_images_game_type_check
    CHECK (game_type IN ('connect', 'dots', 'memory', 'word'));
