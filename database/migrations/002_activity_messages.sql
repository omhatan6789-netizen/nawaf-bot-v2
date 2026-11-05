-- Separate real group activity from message credits obtained by selling points.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS activity_messages BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_users_activity_messages_desc
    ON users(activity_messages DESC)
    WHERE activity_messages > 0;
