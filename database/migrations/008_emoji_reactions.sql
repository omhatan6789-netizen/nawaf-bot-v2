CREATE TABLE IF NOT EXISTS emoji_reaction_rules (
    match_type TEXT NOT NULL CHECK (match_type IN ('exact','contains')),
    keyword TEXT NOT NULL,
    emoji TEXT NOT NULL,
    custom_emoji_id TEXT,
    created_by BIGINT NOT NULL,
    PRIMARY KEY (match_type, keyword)
);
