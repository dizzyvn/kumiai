-- Migration: Add pm_id and team_member_ids to projects table
-- Date: 2025-12-27
-- Description: Add pm_id and team_member_ids columns to support project team configuration

-- Add pm_id column to projects table (character assigned as PM)
ALTER TABLE projects ADD COLUMN pm_id TEXT;

-- Add team_member_ids column to projects table (JSON array of specialist character IDs)
ALTER TABLE projects ADD COLUMN team_member_ids TEXT;

-- Initialize existing projects with empty array for team_member_ids
UPDATE projects SET team_member_ids = '[]' WHERE team_member_ids IS NULL;
