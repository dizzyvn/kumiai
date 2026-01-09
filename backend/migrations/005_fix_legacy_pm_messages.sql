-- Migration to fix legacy PM/Orchestrator messages
-- Legacy messages have role='pm' or role='orchestrator' with agent_name set
-- Should be: role='user', sender_role='pm'/'orchestrator', sender_name from agent_name

-- Fix PM messages
UPDATE session_messages
SET
    role = 'user',
    sender_role = 'pm',
    sender_name = agent_name,
    agent_name = NULL
WHERE role = 'pm';

-- Fix Orchestrator messages
UPDATE session_messages
SET
    role = 'user',
    sender_role = 'orchestrator',
    sender_name = agent_name,
    agent_name = NULL
WHERE role = 'orchestrator';
