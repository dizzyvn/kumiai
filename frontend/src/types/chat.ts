/**
 * Chat and messaging type definitions
 */

export interface ChatContext {
  role: 'orchestrator' | 'pm' | 'specialist' | null;
  name?: string;
  description?: string;
  data?: Record<string, unknown>;
}

export interface ToolUse {
  toolName: string;
  toolArgs?: Record<string, unknown>;
  toolResult?: string; // Tool execution result text (for extracting metadata like instance_id)
}

export interface FileAttachment {
  path: string;
  name: string;
  size: number;
  mimeType?: string;
  thumbnail?: string; // Optional thumbnail URL for images
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool_call';
  content: string;
  toolName?: string; // For tool_call messages
  toolArgs?: Record<string, unknown>; // For tool_call messages
  toolId?: string; // For tool_call messages - Claude's tool use ID
  attachments?: FileAttachment[]; // Structured file attachments
  timestamp: Date;
  isStreaming?: boolean;
  agentName?: string; // Name of the subagent that sent this message
  streamedViaDeltas?: boolean; // True if message was built via stream_delta events
  sender_role?: 'user' | 'pm' | 'orchestrator' | 'specialist'; // Sender attribution (note: 'single_specialist' role is mapped to 'specialist' for display)
  sender_id?: string; // Character ID of the sender (e.g., "alex")
  sender_name?: string; // Display name of the sender (e.g., "Alex")
  sender_instance?: string; // Session instance ID of the sender (e.g., "pm-0b3ce10b")
}
