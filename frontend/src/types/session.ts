/**
 * Unified session types for all session roles.
 *
 * Defines types for orchestrator and PM sessions.
 */

export type SessionRole = 'orchestrator' | 'pm' | 'skill_assistant' | 'character_assistant';

export type SessionStatus = 'idle' | 'working' | 'error' | 'cancelled';

export interface SessionConfig {
  role: SessionRole;
  project_path: string;
  character_id?: string;
  selected_specialists?: string[];
  initial_prompt?: string;
  session_description?: string;
}

export interface SessionInstance {
  instance_id: string;
  role: SessionRole;
  session_id?: string; // Claude SDK session ID
  project_path: string;
  character_id?: string;
  selected_specialists?: string[];
  status: SessionStatus;
  auto_started: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ToolUse {
  name: string;
  id: string;
  input: Record<string, any>;
}

export interface SessionMessage {
  id?: string; // UUID string from database
  instance_id: string;
  role: 'user' | 'assistant' | 'tool_call';
  content: string;
  agent_name?: string; // For specialist messages
  tool_name?: string; // For tool_call messages
  tool_args?: ToolUse[]; // Array of tool uses from Claude API (for tool_call messages)
  sender_role?: 'user' | 'pm' | 'orchestrator'; // Sender attribution
  sender_name?: string; // Display name for sender (e.g., "Project Manager")
  sender_id?: string; // Instance ID of the sender (for identifying which agent sent the message)
  sequence?: number; // Execution order within a response (for ordering tools with text)
  timestamp: string;
  content_type?: string; // "text" or "tool_use" - categorizes content blocks
  response_id?: string; // UUID shared by all blocks in same response
}

// Unified event types from SessionStreamManager
export type SessionEventType =
  | 'stream_delta'
  | 'tool_use'
  | 'tool_complete'
  | 'agent_started'
  | 'agent_delta'
  | 'agent_text'
  | 'agent_tool_use'
  | 'agent_response_complete'
  | 'agent_completed'
  | 'result'
  | 'auto_save'
  | 'status_change'
  | 'error'
  | 'message_complete'
  | 'cancelled'
  | 'user_notification';

export interface BaseSessionEvent {
  type: SessionEventType;
  role: SessionRole;
  timestamp: string;
  event_id?: string; // Optional unique event ID for deduplication
  sequence?: number; // Optional sequence number for ordering
  metadata?: Record<string, any>;
}

export interface StreamDeltaEvent extends BaseSessionEvent {
  type: 'stream_delta';
  content: string;
}

export interface ToolUseEvent extends BaseSessionEvent {
  type: 'tool_use';
  toolName: string;
  toolArgs?: Record<string, unknown>;
}

export interface ToolCompleteEvent extends BaseSessionEvent {
  type: 'tool_complete';
  toolName: string;
  toolArgs: Record<string, unknown>;
}

export interface AgentStartedEvent extends BaseSessionEvent {
  type: 'agent_started';
  agentName: string;
}

export interface AgentDeltaEvent extends BaseSessionEvent {
  type: 'agent_delta';
  agentName: string;
  content: string;
}

export interface AgentTextEvent extends BaseSessionEvent {
  type: 'agent_text';
  agentName: string;
  content: string;
}

export interface AgentToolUseEvent extends BaseSessionEvent {
  type: 'agent_tool_use';
  agentName: string;
  toolName: string;
}

export interface AgentResponseCompleteEvent extends BaseSessionEvent {
  type: 'agent_response_complete';
  agentName: string;
}

export interface AgentCompletedEvent extends BaseSessionEvent {
  type: 'agent_completed';
  agentName: string;
}

export interface ResultEvent extends BaseSessionEvent {
  type: 'result';
  status: 'completed' | 'error';
}

export interface AutoSaveEvent extends BaseSessionEvent {
  type: 'auto_save';
  auto_save_type: 'skill' | 'character';
  item_id: string;
}

export interface StatusChangeEvent extends BaseSessionEvent {
  type: 'status_change';
  status: SessionStatus;
}

export interface ErrorEvent extends BaseSessionEvent {
  type: 'error';
  error: string;
}

export interface MessageCompleteEvent extends BaseSessionEvent {
  type: 'message_complete';
}

export interface CancelledEvent extends BaseSessionEvent {
  type: 'cancelled';
}

export interface UserNotificationEvent extends BaseSessionEvent {
  type: 'user_notification';
  title: string;
  message: string;
  project_name: string;
  priority: 'low' | 'normal' | 'high';
}

export type SessionEvent =
  | StreamDeltaEvent
  | ToolUseEvent
  | ToolCompleteEvent
  | AgentStartedEvent
  | AgentDeltaEvent
  | AgentTextEvent
  | AgentToolUseEvent
  | AgentResponseCompleteEvent
  | AgentCompletedEvent
  | ResultEvent
  | AutoSaveEvent
  | StatusChangeEvent
  | ErrorEvent
  | MessageCompleteEvent
  | CancelledEvent
  | UserNotificationEvent;

// Message filtering configuration
export interface MessageFilterConfig {
  showRoles: Array<'user' | 'assistant' | 'tool'>;
  showAgentNamesOnly?: string[] | null;
  hideOrchestrator: boolean;
}

// Role configuration hints for UI
export interface RoleUIConfig {
  displayName: string;
  icon: string;
  messageFilter: MessageFilterConfig;
  supportsSpecialists: boolean;
  autoSave: boolean;
  autoSaveType?: 'skill' | 'character';
}

// Role configurations for each session type
export const ROLE_UI_CONFIGS: Record<SessionRole, RoleUIConfig> = {
  orchestrator: {
    displayName: 'Orchestrator',
    icon: 'users',
    messageFilter: {
      showRoles: ['user', 'assistant', 'tool_call'],
      showAgentNamesOnly: null, // Show all specialists
      hideOrchestrator: false, // Show all messages including orchestrator
    },
    supportsSpecialists: true,
    autoSave: false,
  },
  pm: {
    displayName: 'Project Manager',
    icon: 'briefcase',
    messageFilter: {
      showRoles: ['user', 'assistant', 'tool_call'],
      showAgentNamesOnly: null,
      hideOrchestrator: false,
    },
    supportsSpecialists: false,
    autoSave: false,
  },
  skill_assistant: {
    displayName: 'Skill Assistant',
    icon: 'wrench',
    messageFilter: {
      showRoles: ['user', 'assistant', 'tool_call'],
      showAgentNamesOnly: null,
      hideOrchestrator: false,
    },
    supportsSpecialists: false,
    autoSave: true,
    autoSaveType: 'skill',
  },
  character_assistant: {
    displayName: 'Character Assistant',
    icon: 'user',
    messageFilter: {
      showRoles: ['user', 'assistant', 'tool_call'],
      showAgentNamesOnly: null,
      hideOrchestrator: false,
    },
    supportsSpecialists: false,
    autoSave: true,
    autoSaveType: 'character',
  },
};

// Helper function to filter messages based on role
export function filterMessagesByRole(
  messages: SessionMessage[],
  role: SessionRole
): SessionMessage[] {
  const config = ROLE_UI_CONFIGS[role];
  const filter = config.messageFilter;

  return messages.filter((msg) => {
    // Filter by role
    if (!filter.showRoles.includes(msg.role as any)) {
      return false;
    }

    // Hide orchestrator messages if configured
    if (filter.hideOrchestrator && msg.role === 'assistant' && !msg.agent_name) {
      return false;
    }

    // Filter by agent names if specified
    if (filter.showAgentNamesOnly && msg.agent_name) {
      return filter.showAgentNamesOnly.includes(msg.agent_name);
    }

    return true;
  });
}

// Helper function to get role config
export function getRoleConfig(role: SessionRole): RoleUIConfig {
  return ROLE_UI_CONFIGS[role];
}
