-- Per-group Telegram Stars subscriptions.
CREATE TABLE IF NOT EXISTS stars_subscription_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    price_stars INTEGER NOT NULL DEFAULT 1 CHECK (price_stars >= 1),
    duration_days INTEGER NOT NULL DEFAULT 30 CHECK (duration_days >= 1),
    sales_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO stars_subscription_settings (id, price_stars, duration_days, sales_enabled)
VALUES (1, 1, 30, FALSE)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS stars_subscription_orders (
    payload TEXT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    created_by BIGINT NOT NULL,
    amount_stars INTEGER NOT NULL,
    duration_days INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_stars_orders_chat ON stars_subscription_orders(chat_id, created_at DESC);

CREATE TABLE IF NOT EXISTS stars_subscription_payments (
    charge_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL UNIQUE REFERENCES stars_subscription_orders(payload),
    chat_id BIGINT NOT NULL,
    payer_id BIGINT NOT NULL,
    amount_stars INTEGER NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stars_group_subscriptions (
    chat_id BIGINT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    last_charge_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
