-- Add path field to projects table
ALTER TABLE projects ADD COLUMN path VARCHAR(512);

-- Update existing projects with default paths
-- Note: This uses a placeholder path. Actual paths are managed by backend.core.config.settings
UPDATE projects SET path = './projects/' || id WHERE path IS NULL;

-- Make path not null now that all have values
-- ALTER TABLE projects ALTER COLUMN path SET NOT NULL;  -- Comment out for SQLite compatibility
