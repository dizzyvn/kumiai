-- User Profile Migration
-- Date: 2026-01-09
-- Description: Add user_profile table for personalizing AI interactions

-- Create user_profile table (singleton - only one record)
CREATE TABLE IF NOT EXISTS user_profile (
    id VARCHAR PRIMARY KEY DEFAULT 'default',
    avatar TEXT,  -- Avatar URL or base64 data URI
    description TEXT,  -- User description (who you are, what you do)
    preferences TEXT,  -- User preferences (communication style, etc.)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
);

-- Ensure only one record exists (singleton pattern)
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profile_singleton ON user_profile(id);
