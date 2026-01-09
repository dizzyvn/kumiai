-- Migration: Add auto_started column to sessions table
-- Date: 2025-12-27
-- Description: Adds auto_started boolean column to track sessions that were started in background

-- Add auto_started column with default value FALSE
ALTER TABLE sessions ADD COLUMN auto_started BOOLEAN DEFAULT 0;

-- Update existing rows to have auto_started = FALSE (0)
UPDATE sessions SET auto_started = 0 WHERE auto_started IS NULL;
