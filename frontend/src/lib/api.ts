// API client for backend
// Use environment variable or construct from current hostname
const getApiBase = () => {
  // Check if we have an environment variable
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // Use configurable port from environment or default
  const port = import.meta.env.VITE_API_PORT || '7892';

  // If running in browser, use current hostname
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    return `http://${hostname}:${port}`;
  }

  // Fallback to localhost
  return `http://localhost:${port}`;
};

const API_BASE = getApiBase();

export interface AgentCharacter {
  id: string;
  name: string;
  avatar: string;
  description: string;
  color: string;
  skills: string[];
  default_model: string;
  personality?: string;
}

export interface AgentInstance {
  instance_id: string;
  character: AgentCharacter;
  pid?: number;
  role?: 'orchestrator' | 'pm' | 'specialist';
  status: 'idle' | 'thinking' | 'working' | 'waiting' | 'completed' | 'error';
  current_session_description?: string;
  project_id: string;
  project_path: string;
  session_id?: string;
  started_at: string;
  output_lines: number;
  // Kanban workflow stage
  kanban_stage?: 'backlog' | 'active' | 'blocked' | 'review' | 'done';
  // Actual capabilities from Claude's init message
  actual_tools?: string[];
  selected_specialists?: string[];  // Team members selected for this agent
  actual_mcp_servers?: any[];
  actual_skills?: string[];
  auto_started?: boolean;  // Whether session was auto-started in background
}

export interface SpawnAgentRequest {
  team_member_ids: string[];  // Specialists to make available
  project_id?: string;  // If not provided, defaults to "default" project
  project_path: string;
  session_description: string;
  model?: string;
  system_prompt_append?: string;  // Additional instructions to append to system prompt
  role?: 'orchestrator' | 'pm' | 'specialist' | 'single_specialist' | 'character_assistant' | 'skill_assistant';
  auto_start?: boolean;  // If true, starts execution in background immediately
  kanban_stage?: string;  // Add missing kanban_stage field
}

export interface SessionMessage {
  id: string;
  instance_id: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  agent_name?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  timestamp: string;
  cost_usd?: number;
  is_streaming: boolean;
  sender_role?: 'user' | 'pm' | 'orchestrator' | 'single_specialist' | 'specialist';
  sender_id?: string;  // Character ID of the sender (e.g., "alex")
  sender_name?: string;  // Display name of the sender (e.g., "Alex")
  sender_instance?: string;  // Session instance ID of the sender (e.g., "pm-0b3ce10b")
}

export interface SendMessageRequest {
  content: string;
  query_type?: 'normal' | 'interrupt';
  sender_role?: 'user' | 'pm' | 'orchestrator';
  sender_name?: string;
}

export interface SendMessageResponse {
  status: 'queued';
  queue_size: number;
  processing: boolean;
}

export interface QueueStatus {
  queue_size: number;
  is_processing: boolean;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  path?: string;
  pm_id?: string;
  team_member_ids?: string[];
  createdAt: string;
  updatedAt?: string;
  is_archived?: boolean;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  path?: string;
  pm_id?: string;
  team_member_ids?: string[];
  id?: string;
}

export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  pm_id?: string;
  team_member_ids?: string[];
  is_archived?: boolean;
}

export const api = {
  async getCharacters(): Promise<AgentCharacter[]> {
    const res = await fetch(`${API_BASE}/characters`);
    return res.json();
  },

  async launchSession(req: SpawnAgentRequest): Promise<AgentInstance> {
    // Use unified /sessions/launch endpoint for all roles
    const res = await fetch(`${API_BASE}/sessions/launch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getSessions(): Promise<AgentInstance[]> {
    const res = await fetch(`${API_BASE}/sessions`);
    return res.json();
  },

  async getSession(sessionId: string): Promise<AgentInstance> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
    return res.json();
  },

  async getSessionMessages(sessionId: string, limit: number = 100): Promise<SessionMessage[]> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages?limit=${limit}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  streamSessionOutput(sessionId: string, onEvent: (event: any) => void) {
    console.log(`[STREAM] Connecting to: ${API_BASE}/sessions/${sessionId}/stream`);
    const eventSource = new EventSource(`${API_BASE}/sessions/${sessionId}/stream`);

    eventSource.onopen = () => {
      console.log('[STREAM] Connection opened');
    };

    eventSource.onmessage = (e) => {
      console.log('[STREAM] Message received:', e.data);
      try {
        const event = JSON.parse(e.data);
        console.log('[STREAM] Parsed event:', event);
        onEvent(event);

        // Close on complete or error
        if (event.type === 'complete' || event.type === 'error') {
          console.log('[STREAM] Stream ended:', event.type);
          eventSource.close();
        }
      } catch (parseError) {
        console.error('[STREAM] Failed to parse event:', parseError, 'Raw data:', e.data);
      }
    };

    eventSource.onerror = (error) => {
      console.error('[STREAM] EventSource error:', error);
      console.error('[STREAM] EventSource readyState:', eventSource.readyState);
      // Send error event to handler
      onEvent({ type: 'error', data: { error: 'Connection error' } });
      eventSource.close();
    };

    return () => {
      console.log('[STREAM] Closing connection');
      eventSource.close();
    };
  },

  async sendMessageToSession(
    sessionId: string,
    request: SendMessageRequest | string
  ): Promise<SendMessageResponse> {
    // Support both old string format and new request object
    const body: SendMessageRequest = typeof request === 'string'
      ? { content: request }
      : request;

    console.log(`[API] Sending message to session ${sessionId}:`, body);
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const error = await res.text();
      console.error('[API] Failed to send message:', error);
      throw new Error(error);
    }
    const response = await res.json();
    console.log('[API] Message queued:', response);
    return response;
  },

  async getQueueStatus(sessionId: string): Promise<QueueStatus> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/queue-status`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async cancelSession(sessionId: string): Promise<void> {
    await fetch(`${API_BASE}/sessions/${sessionId}/cancel`, {
      method: 'POST',
    });
  },

  async updateSessionStage(sessionId: string, stage: string): Promise<void> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/stage`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage }),
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async deleteSession(sessionId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },


  // Project Management
  async getProjects(includeArchived: boolean = false): Promise<Project[]> {
    const params = new URLSearchParams();
    if (includeArchived) {
      params.append('include_archived', 'true');
    }
    const url = `${API_BASE}/projects${params.toString() ? '?' + params.toString() : ''}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getProject(projectId: string): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async createProject(req: CreateProjectRequest): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateProject(projectId: string, req: UpdateProjectRequest): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteProject(projectId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async unarchiveProject(projectId: string): Promise<{ message: string; project_id: string }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/unarchive`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async permanentlyDeleteProject(projectId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/permanent`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async recreatePmSession(projectId: string): Promise<{ status: string; message: string; pm_instance_id: string }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/recreate-pm`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async recreateSkillAssistant(): Promise<{ status: string; message: string; instance_id: string }> {
    const res = await fetch(`${API_BASE}/sessions/skill-assistant/recreate`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async recreateCharacterAssistant(): Promise<{ status: string; message: string; instance_id: string }> {
    const res = await fetch(`${API_BASE}/sessions/character-assistant/recreate`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Project File Management
  async getProjectFileContent(projectId: string, filePath: string): Promise<{ content: string; path: string; readonly: boolean }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/files/content?file_path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateProjectFileContent(projectId: string, filePath: string, content: string): Promise<void> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/files/content`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, content }),
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async deleteProjectFile(projectId: string, filePath: string): Promise<void> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/files?file_path=${encodeURIComponent(filePath)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async downloadProjectFile(projectId: string, filePath: string): Promise<Blob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/files/download?file_path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.blob();
  },

  // Session File Management
  async getSessionFileContent(sessionId: string, filePath: string): Promise<{ content: string; path: string; readonly: boolean }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/files/content?file_path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateSessionFileContent(sessionId: string, filePath: string, content: string): Promise<void> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/files/content`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, content }),
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async deleteSessionFile(sessionId: string, filePath: string): Promise<void> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/files?file_path=${encodeURIComponent(filePath)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async downloadSessionFile(sessionId: string, filePath: string): Promise<Blob> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/files/download?file_path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.blob();
  },

  // Skill Management
  async getSkills(): Promise<SkillMetadata[]> {
    const res = await fetch(`${API_BASE}/skills`);
    return res.json();
  },

  async getSkill(skillId: string): Promise<SkillDefinition> {
    const res = await fetch(`${API_BASE}/skills/${skillId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async searchSkills(query: string): Promise<SkillSearchResponse> {
    const res = await fetch(`${API_BASE}/skills/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async createSkill(req: CreateSkillRequest): Promise<SkillDefinition> {
    const res = await fetch(`${API_BASE}/skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateSkill(skillId: string, req: UpdateSkillRequest): Promise<SkillDefinition> {
    const res = await fetch(`${API_BASE}/skills/${skillId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async syncSkill(skillId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/skills/${skillId}/sync`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async deleteSkill(skillId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/skills/${skillId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async importSkill(req: ImportSkillRequest): Promise<ImportSkillResponse> {
    const res = await fetch(`${API_BASE}/skills/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getMcpServers(): Promise<McpServer[]> {
    const res = await fetch(`${API_BASE}/mcp/servers`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getCustomTools(): Promise<CustomTool[]> {
    const res = await fetch(`${API_BASE}/skills/tools/custom`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async promptEditSkill(skillId: string | null, prompt: string): Promise<{ agent_id: string; message: string; status: string }> {
    const res = await fetch(`${API_BASE}/skills/prompt-edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_id: skillId, prompt }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getSkillFiles(skillId: string): Promise<SkillFileNode[]> {
    const res = await fetch(`${API_BASE}/skills/${skillId}/files`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getSkillFileContent(skillId: string, filePath: string): Promise<{ content: string; path: string }> {
    const res = await fetch(`${API_BASE}/skills/${skillId}/files/content?file_path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateSkillFileContent(skillId: string, filePath: string, content: string): Promise<void> {
    const res = await fetch(`${API_BASE}/skills/${skillId}/files/content`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, content }),
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async deleteSkillFile(skillId: string, filePath: string): Promise<void> {
    const res = await fetch(`${API_BASE}/skills/${skillId}/files?file_path=${encodeURIComponent(filePath)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async renameSkillFile(skillId: string, oldPath: string, newPath: string): Promise<void> {
    const res = await fetch(`${API_BASE}/skills/${skillId}/files/rename`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
    });
    if (!res.ok) throw new Error(await res.text());
  },

  // Character Management
  async getCharactersLibrary(): Promise<CharacterMetadata[]> {
    const res = await fetch(`${API_BASE}/characters`);
    return res.json();
  },

  async getCharacterLibrary(characterId: string): Promise<CharacterDefinition> {
    const res = await fetch(`${API_BASE}/characters/${characterId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async createCharacter(req: CreateCharacterRequest): Promise<CharacterDefinition> {
    console.log('API: Creating character with request:', req);
    console.log('API: Sending POST to:', `${API_BASE}/characters`);
    try {
      const res = await fetch(`${API_BASE}/characters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      console.log('API: Response status:', res.status);
      if (!res.ok) {
        const errorText = await res.text();
        console.error('API: Error response:', errorText);
        throw new Error(errorText);
      }
      const data = await res.json();
      console.log('API: Success response:', data);
      return data;
    } catch (error) {
      console.error('API: Request failed:', error);
      throw error;
    }
  },

  async updateCharacter(characterId: string, req: UpdateCharacterRequest): Promise<CharacterDefinition> {
    const res = await fetch(`${API_BASE}/characters/${characterId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteCharacter(characterId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/characters/${characterId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async syncCharacter(characterId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/characters/sync/${characterId}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async promptEditCharacter(characterId: string | null, prompt: string): Promise<{ agent_id: string; message: string; status: string }> {
    const res = await fetch(`${API_BASE}/characters/prompt-edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_id: characterId, prompt }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getCharacterFiles(characterId: string): Promise<SkillFileNode[]> {
    const res = await fetch(`${API_BASE}/characters/${characterId}/files`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getCharacterFileContent(characterId: string, filePath: string): Promise<{ content: string; path: string }> {
    const res = await fetch(`${API_BASE}/characters/${characterId}/files/content?file_path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateCharacterFileContent(characterId: string, filePath: string, content: string): Promise<void> {
    const res = await fetch(`${API_BASE}/characters/${characterId}/files/content`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, content }),
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async deleteCharacterFile(characterId: string, filePath: string): Promise<void> {
    const res = await fetch(`${API_BASE}/characters/${characterId}/files?file_path=${encodeURIComponent(filePath)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
  },

  async renameCharacterFile(characterId: string, oldPath: string, newPath: string): Promise<void> {
    const res = await fetch(`${API_BASE}/characters/${characterId}/files/rename`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
    });
    if (!res.ok) throw new Error(await res.text());
  },

  // User Profile API
  async getUserProfile(): Promise<UserProfile> {
    const res = await fetch(`${API_BASE}/user-profile`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateUserProfile(data: UpdateUserProfileRequest): Promise<UserProfile> {
    const res = await fetch(`${API_BASE}/user-profile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

export interface SkillMetadata {
  id: string;
  name: string;
  description: string;
  has_scripts: boolean;
  has_resources: boolean;
  icon?: string;
  iconColor?: string;
}

export interface SkillDefinition {
  id: string;
  name: string;
  description: string;
  content: string;
  license: string;
  version: string;
  icon?: string;
  iconColor?: string;
}

export interface SkillSearchResult {
  skill: SkillMetadata;
  score: number;
  match_field: string;
  match_text: string;
}

export interface SkillSearchResponse {
  query: string;
  results: SkillSearchResult[];
}

export interface CreateSkillRequest {
  id: string;
  name: string;
  description: string;
  content?: string;
  license?: string;
  version?: string;
  icon?: string;
  iconColor?: string;
}

export interface UpdateSkillRequest {
  name?: string;
  description?: string;
  content?: string;
  license?: string;
  version?: string;
  icon?: string;
  iconColor?: string;
}

export interface ImportSkillRequest {
  source: string;
  skill_id?: string;
}

export interface ImportSkillResponse {
  skill: SkillDefinition;
  status: string;
  message: string;
}

export interface McpServer {
  id: string;
  name: string;
  command: string;
  description: string;
}

export interface CustomTool {
  id: string;
  provider: string;
  category: string;
  name: string;
  description: string;
  input_schema: Record<string, any>;
}

export interface CharacterCapabilities {
  allowed_tools: string[];
  allowed_agents: string[];
  allowed_mcp_servers: string[];
  allowed_skills: string[];
  allowed_slash_commands: string[];
}

export interface CharacterMetadata {
  id: string;
  name: string;
  avatar?: string;
  description?: string;
  color?: string;
  skills?: string[];  // Skill IDs for display
}

export interface CharacterDefinition {
  id: string;
  name: string;
  avatar: string;
  description: string;
  color: string;
  default_model: string;
  personality?: string;
  capabilities: CharacterCapabilities;
}

export interface CreateCharacterRequest {
  name: string;
  description: string;
  default_model?: string;
  id?: string;
  avatar?: string;
  color?: string;
  personality?: string;
  capabilities?: CharacterCapabilities;
  skills?: string[];  // Deprecated: use capabilities.allowed_skills
}

export interface UpdateCharacterRequest {
  name?: string;
  avatar?: string;
  description?: string;
  color?: string;
  default_model?: string;
  personality?: string;
  capabilities?: CharacterCapabilities;
  skills?: string[];  // Deprecated: use capabilities.allowed_skills
}

export interface UserProfile {
  id: string;
  avatar?: string;
  description?: string;
  preferences?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UpdateUserProfileRequest {
  avatar?: string;
  description?: string;
  preferences?: string;
}
