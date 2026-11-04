-- Migration 004: Demon Nawaf character catalog and per-user game sessions.
CREATE TABLE IF NOT EXISTS demon_nawaf_characters (
    slug TEXT PRIMARY KEY,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    category_ar TEXT NOT NULL DEFAULT 'شخصية',
    category_en TEXT NOT NULL DEFAULT 'Character',
    wiki_title TEXT NOT NULL DEFAULT '',
    traits TEXT NOT NULL DEFAULT '[]',
    image_url TEXT NOT NULL DEFAULT '',
    summary_ar TEXT NOT NULL DEFAULT '',
    summary_en TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'seed',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demon_nawaf_sessions (
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    lang TEXT NOT NULL DEFAULT 'ar',
    state TEXT NOT NULL DEFAULT 'language',
    answers TEXT NOT NULL DEFAULT '{}',
    asked TEXT NOT NULL DEFAULT '[]',
    excluded TEXT NOT NULL DEFAULT '[]',
    guesses TEXT NOT NULL DEFAULT '[]',
    question_count INTEGER NOT NULL DEFAULT 0,
    current_question TEXT NOT NULL DEFAULT '',
    last_rejected_at INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, chat_id)
);

CREATE INDEX IF NOT EXISTS idx_demon_nawaf_session_state
    ON demon_nawaf_sessions(state);
