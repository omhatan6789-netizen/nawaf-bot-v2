-- A group invoice may be paid by more than one member; each successful payment extends the same group subscription.
ALTER TABLE stars_subscription_payments
    DROP CONSTRAINT IF EXISTS stars_subscription_payments_payload_key;
