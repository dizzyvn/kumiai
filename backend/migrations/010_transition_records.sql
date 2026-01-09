-- Add content_type field to session_messages table
-- This enables categorizing messages as text vs tool_use content blocks
-- When content type changes (text→tool, tool→tool, tool→text), we finalize the current block

-- Add content_type column to categorize messages
ALTER TABLE session_messages
ADD COLUMN content_type TEXT DEFAULT 'text' CHECK(content_type IN ('text', 'tool_use'));

-- Backfill content_type for existing records
UPDATE session_messages
SET content_type = CASE
    WHEN role = 'tool_call' THEN 'tool_use'
    ELSE 'text'
END
WHERE content_type = 'text';  -- Only update default values

-- Create index for querying by content_type (useful for analytics)
CREATE INDEX IF NOT EXISTS idx_session_messages_content_type
ON session_messages(instance_id, content_type);
