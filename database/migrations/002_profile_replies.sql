-- Migration 002: profile cards, group owner overrides, and admin replies.
-- Fresh schema only; no legacy data is imported.

CREATE TABLE IF NOT EXISTS group_profile_settings (
    chat_id BIGINT PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    owner_user_id BIGINT,
    owner_username TEXT,
    admin_replies_enabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS admin_replies (
    chat_id BIGINT NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    admin_user_id BIGINT NOT NULL,
    reply_name TEXT NOT NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chat_id, admin_user_id),
    UNIQUE (chat_id, reply_name)
);

CREATE INDEX IF NOT EXISTS idx_admin_replies_chat_created
    ON admin_replies(chat_id, created_date, admin_user_id);

INSERT INTO profile_settings(profile_type, user_id, username)
VALUES ('developer', 8453977662, NULL)
ON CONFLICT (profile_type) DO NOTHING;
