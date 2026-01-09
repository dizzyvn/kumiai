-- Tool Result Fields Migration
-- Date: 2026-01-07
-- Description: Add tool_use_id and is_error fields to session_messages table for tool result tracking

-- Step 1: Add tool_use_id column (for linking tool_call to tool_result)
ALTER TABLE session_messages ADD COLUMN tool_use_id VARCHAR(255);

-- Step 2: Add is_error column (for tool_result error indication)
ALTER TABLE session_messages ADD COLUMN is_error BOOLEAN DEFAULT 0;

-- Step 3: Create index for efficient tool result lookups
CREATE INDEX IF NOT EXISTS idx_tool_use_id ON session_messages(tool_use_id);
