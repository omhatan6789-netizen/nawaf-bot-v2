CREATE TABLE IF NOT EXISTS mini_app_button_colors (
    button_text TEXT PRIMARY KEY,
    color_hex TEXT NOT NULL CHECK (color_hex ~ '^#[0-9a-fA-F]{6}$'),
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
