ALTER TABLE casual_game_rooms
    DROP CONSTRAINT IF EXISTS casual_game_rooms_game_type_check;

ALTER TABLE casual_game_rooms
    ADD CONSTRAINT casual_game_rooms_game_type_check
    CHECK (game_type IN ('match', 'number', 'find'));
