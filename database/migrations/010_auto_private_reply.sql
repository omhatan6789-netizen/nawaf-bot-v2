-- Migration 010: one automatic private reply per user every 24 hours.
CREATE TABLE IF NOT EXISTS auto_private_replied (
    user_id BIGINT PRIMARY KEY,
    replied_at BIGINT NOT NULL
);
