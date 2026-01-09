-- Add sender attribution fields to session_messages table
-- This allows tracking WHO sent each message (user, PM, orchestrator)

-- Add sender_role column
ALTER TABLE session_messages
ADD COLUMN sender_role TEXT;

-- Add sender_name column
ALTER TABLE session_messages
ADD COLUMN sender_name TEXT;

-- Update existing messages to have sender_role = 'user' for user messages
UPDATE session_messages
SET sender_role = 'user'
WHERE role = 'user' AND sender_role IS NULL;

-- Create index for sender queries
CREATE INDEX IF NOT EXISTS idx_session_messages_sender_role
ON session_messages(instance_id, sender_role);
