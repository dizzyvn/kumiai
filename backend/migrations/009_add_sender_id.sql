-- Add sender_id field to session_messages table
-- This tracks the instance_id of the sender for cross-session messages

-- Add sender_id column
ALTER TABLE session_messages
ADD COLUMN sender_id TEXT;

-- Create index for sender_id queries
CREATE INDEX IF NOT EXISTS idx_session_messages_sender_id
ON session_messages(sender_id);
