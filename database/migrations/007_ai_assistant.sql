-- Migration 007: per-chat AI assistant settings.
CREATE TABLE IF NOT EXISTS ai_assistant_settings (
    chat_id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
