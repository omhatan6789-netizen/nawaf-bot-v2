ALTER TABLE mini_app_settings
    ADD COLUMN IF NOT EXISTS banner_media_kind TEXT NOT NULL DEFAULT 'image',
    ADD COLUMN IF NOT EXISTS banner_mime_type TEXT;
