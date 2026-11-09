ALTER TABLE mini_app_buttons
    ADD COLUMN IF NOT EXISTS media_kind TEXT NOT NULL DEFAULT 'image',
    ADD COLUMN IF NOT EXISTS mime_type TEXT;
