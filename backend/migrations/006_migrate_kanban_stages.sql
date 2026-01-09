-- Migration: Update Kanban stages from 5-column to 4-column layout
-- Old: backlog, active, blocked, review, done
-- New: backlog, active, waiting, done
--
-- This migration maps:
-- - blocked → waiting
-- - review → waiting

-- Update blocked stages to waiting
UPDATE sessions
SET kanban_stage = 'waiting'
WHERE kanban_stage = 'blocked';

-- Update review stages to waiting
UPDATE sessions
SET kanban_stage = 'waiting'
WHERE kanban_stage = 'review';

-- Report results
SELECT
    'Migration complete' as status,
    COUNT(CASE WHEN kanban_stage = 'waiting' THEN 1 END) as waiting_count,
    COUNT(CASE WHEN kanban_stage = 'active' THEN 1 END) as active_count,
    COUNT(CASE WHEN kanban_stage = 'backlog' THEN 1 END) as backlog_count,
    COUNT(CASE WHEN kanban_stage = 'done' THEN 1 END) as done_count
FROM sessions;
