-- Migration 011: Add response_id field for grouping messages from the same query response
-- This enables the frontend to display all messages (text blocks + tool uses) from a single
-- response in the same UI bubble.

-- Add response_id column
ALTER TABLE session_messages
ADD COLUMN response_id TEXT;

-- Backfill existing messages: Group messages by instance_id and timestamp proximity
-- Messages within 1 second of each other from the same instance are considered part
-- of the same response. This is a best-effort backfill for existing data.
UPDATE session_messages
SET response_id = (
    SELECT DISTINCT first_value(id) OVER (
        PARTITION BY instance_id,
        CAST((julianday(timestamp) * 86400) / 1 AS INTEGER)
        ORDER BY timestamp
    )
    FROM session_messages sm2
    WHERE sm2.id = session_messages.id
);

-- Create index for efficient querying by response_id
CREATE INDEX IF NOT EXISTS idx_instance_response_id
ON session_messages(instance_id, response_id);

-- Note: For new messages, response_id should be generated when starting a new response
-- and passed to all message records created during that response's streaming.
