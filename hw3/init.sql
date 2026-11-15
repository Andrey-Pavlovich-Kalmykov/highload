CREATE TABLE IF NOT EXISTS processed_events (
    event_id UUID PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    seq INT NOT NULL,
    consumer_pod VARCHAR NOT NULL,
    topic VARCHAR NOT NULL,
    partition INT NOT NULL,
    offset_val BIGINT NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS duplicates_counter (
    event_id UUID,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);