-- Message Sequence Migration
-- Date: 2026-01-08
-- Description: Add sequence column to session_messages for preserving execution order

-- Add sequence column (for ordering tool calls with text in execution order)
ALTER TABLE session_messages ADD COLUMN sequence INTEGER DEFAULT 0;

-- Note: No index needed as sequence is only used for sorting within a single message group
