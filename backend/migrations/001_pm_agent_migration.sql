-- PM Agent Migration
-- Date: 2024-12-26
-- Description: Add role field, rename kanban stages, add PM uniqueness constraint

-- Step 1: Add role column with default value
ALTER TABLE sessions ADD COLUMN role VARCHAR(20) DEFAULT 'orchestrator';

-- Step 2: Ensure all existing rows have role set
UPDATE sessions SET role = 'orchestrator' WHERE role IS NULL;

-- Step 3: Migrate kanban_stage values to new names
UPDATE sessions SET kanban_stage = 'active' WHERE kanban_stage = 'in_progress';
UPDATE sessions SET kanban_stage = 'blocked' WHERE kanban_stage = 'waiting';
UPDATE sessions SET kanban_stage = 'done' WHERE kanban_stage = 'complete';

-- Step 4: Add unique constraint (one PM per project)
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pm_per_project
ON sessions(project_id)
WHERE role = 'pm' AND status != 'cancelled';
