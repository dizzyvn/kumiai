"""Pydantic schemas for API request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ============================================================================
# Character Schemas
# ============================================================================

class CharacterCapabilities(BaseModel):
    """Character capabilities configuration."""

    allowed_tools: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)
    allowed_mcp_servers: list[str] = Field(default_factory=list)
    allowed_custom_tools: list[str] = Field(default_factory=list)
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_slash_commands: list[str] = Field(default_factory=list)


class CharacterMetadata(BaseModel):
    """Character metadata (lightweight for list view)."""

    id: str
    name: str
    avatar: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    skills: list[str] = Field(default_factory=list)  # Skill IDs for display


class CharacterDefinition(CharacterMetadata):
    """Full character definition."""

    default_model: str = "sonnet"
    personality: Optional[str] = None
    capabilities: Optional[CharacterCapabilities] = None


class CreateCharacterRequest(BaseModel):
    """Request to create a new character."""

    name: str
    description: Optional[str] = None
    default_model: Optional[str] = "sonnet"
    id: Optional[str] = None
    avatar: Optional[str] = None
    color: Optional[str] = None
    personality: Optional[str] = None
    capabilities: Optional[CharacterCapabilities] = None
    skills: Optional[list[str]] = None  # Deprecated: use capabilities.allowed_skills


class UpdateCharacterRequest(BaseModel):
    """Request to update a character."""

    name: Optional[str] = None
    avatar: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    default_model: Optional[str] = None
    personality: Optional[str] = None
    capabilities: Optional[CharacterCapabilities] = None
    skills: Optional[list[str]] = None  # Deprecated


# ============================================================================
# Project Schemas
# ============================================================================

class ProjectMetadata(BaseModel):
    """Project metadata."""

    id: str
    name: str
    description: Optional[str] = None
    path: Optional[str] = None
    pm_id: Optional[str] = None
    team_member_ids: Optional[list[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_archived: bool = False


class CreateProjectRequest(BaseModel):
    """Request to create a new project."""

    name: str
    description: Optional[str] = None
    path: Optional[str] = None
    pm_id: Optional[str] = None
    team_member_ids: Optional[list[str]] = None
    id: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    """Request to update a project."""

    name: Optional[str] = None
    description: Optional[str] = None
    pm_id: Optional[str] = None
    team_member_ids: Optional[list[str]] = None
    is_archived: Optional[bool] = None


# ============================================================================
# Agent Instance Schemas
# ============================================================================

class AgentCharacter(BaseModel):
    """Character info for agent instance."""

    id: str
    name: str
    avatar: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    default_model: str = "sonnet"
    personality: Optional[str] = None


class AgentInstance(BaseModel):
    """Active agent instance."""

    instance_id: str
    character: AgentCharacter
    pid: Optional[int] = None
    role: str = "orchestrator"  # orchestrator, pm, specialist
    status: str = "idle"
    current_session_description: Optional[str] = None
    project_id: str
    project_path: str
    session_id: Optional[str] = None
    started_at: datetime
    output_lines: int = 0
    kanban_stage: Optional[str] = "backlog"
    selected_specialists: Optional[list[str]] = None  # Team members selected for this agent
    actual_tools: Optional[list[str]] = None
    actual_mcp_servers: Optional[list] = None
    actual_skills: Optional[list[str]] = None
    auto_started: Optional[bool] = False  # Whether session was auto-started in background


class SpawnAgentRequest(BaseModel):
    """Request to spawn a new agent."""

    team_member_ids: list[str] = Field(default_factory=list)
    project_id: Optional[str] = None  # If not provided, defaults to "default" project
    project_path: str
    session_description: str  # Short description (metadata only, not sent to agent)
    model: Optional[str] = None
    system_prompt_append: Optional[str] = None  # Additional instructions to append to system prompt
    role: Optional[str] = "orchestrator"  # orchestrator, pm, specialist, or character_assistant
    # Note: Sessions always start in 'backlog' and activate when receiving first message


class UpdateAgentStageRequest(BaseModel):
    """Request to update agent kanban stage."""

    stage: str


# ============================================================================
# Skill Schemas
# ============================================================================

class SkillMetadata(BaseModel):
    """Skill metadata (lightweight for list view).

    Skills are pure documentation - no tool/MCP server declarations.
    """

    id: str
    name: str
    description: Optional[str] = None
    has_scripts: bool = False
    has_resources: bool = False
    icon: Optional[str] = None
    iconColor: Optional[str] = None


class SkillDefinition(BaseModel):
    """Full skill definition.

    Skills are pure documentation - no tool/MCP server declarations.
    Tool and MCP server requirements are in Character database.
    """

    id: str
    name: str
    description: Optional[str] = None
    content: Optional[str] = None
    license: str = "Apache-2.0"
    version: str = "1.0.0"
    icon: Optional[str] = None
    iconColor: Optional[str] = None


class CreateSkillRequest(BaseModel):
    """Request to create a new skill (pure documentation)."""

    id: str
    name: str
    description: Optional[str] = None
    content: Optional[str] = None
    license: Optional[str] = "Apache-2.0"
    version: Optional[str] = "1.0.0"
    icon: Optional[str] = None
    iconColor: Optional[str] = None


class UpdateSkillRequest(BaseModel):
    """Request to update a skill (pure documentation)."""

    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    license: Optional[str] = None
    version: Optional[str] = None
    icon: Optional[str] = None
    iconColor: Optional[str] = None


class SkillSearchResult(BaseModel):
    """Search result for a skill."""

    skill: SkillMetadata
    score: int = Field(..., ge=0, le=100, description="Match score (0-100)")
    match_field: str = Field(..., description="Field where match was found (name, description, id)")
    match_text: str = Field(..., description="Text that matched the query")


class SkillSearchResponse(BaseModel):
    """Response for skill search."""

    query: str
    results: list[SkillSearchResult] = Field(default_factory=list)


class ImportSkillRequest(BaseModel):
    """Request to import a skill from external source."""

    source: str = Field(..., description="GitHub URL or local directory path")
    skill_id: Optional[str] = Field(None, description="Optional custom skill ID (auto-generated if not provided)")


class ImportSkillResponse(BaseModel):
    """Response for skill import."""

    skill: SkillDefinition
    status: str = "success"
    message: str


# ============================================================================
# File Management Schemas
# ============================================================================

class FileContentRequest(BaseModel):
    """Request to update file content."""

    file_path: str
    content: str


class FileContentResponse(BaseModel):
    """Response with file content."""

    path: str
    content: str
    readonly: bool = False


class PreparedFileInfo(BaseModel):
    """Information about a prepared (temp uploaded) file."""

    id: str  # Temp file ID (e.g., "temp_abc123_data.json")
    name: str  # Original filename
    size: int  # File size in bytes
    type: str  # MIME type
    expires_at: str  # ISO 8601 timestamp


class FileUploadError(BaseModel):
    """Error information for failed file operation."""

    name: str  # Filename or file ID
    error: str  # Error message


class FilePrepareResponse(BaseModel):
    """Response from file prepare endpoint."""

    prepared: list[PreparedFileInfo]
    errors: list[FileUploadError]


class CommittedFileInfo(BaseModel):
    """Information about a committed (moved to session) file."""

    name: str  # Final filename
    path: str  # Relative path in session (e.g., "working/data.json")
    size: int  # File size in bytes
    type: str  # MIME type


class FileCommitRequest(BaseModel):
    """Request to commit prepared files to session."""

    file_ids: list[str]  # List of temp file IDs to commit
    target_dir: str = "working"  # Target directory: "working" or "result"


class FileCommitResponse(BaseModel):
    """Response from file commit endpoint."""

    committed: list[CommittedFileInfo]
    errors: list[FileUploadError]


# ============================================================================
# Message Schemas
# ============================================================================

class SessionMessage(BaseModel):
    """Session conversation message."""

    id: str
    instance_id: str
    role: str  # user, assistant, tool_call, tool_result, system
    content: str
    agent_name: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[list[dict]] = None  # List of tool uses: [{"name": "...", "id": "...", "input": {...}}]
    tool_use_id: Optional[str] = None  # Claude's tool use ID for tool results
    is_error: bool = False  # Whether tool result is an error
    sender_role: Optional[str] = None  # "user", "pm", "orchestrator"
    sender_id: Optional[str] = None  # Character ID of the sender (e.g., "alex")
    sender_name: Optional[str] = None  # Display name of sender (e.g., "Alex")
    sender_instance: Optional[str] = None  # Session instance ID (e.g., "pm-0b3ce10b")
    sequence: int = 0  # Execution order within a response
    timestamp: datetime
    cost_usd: Optional[float] = None
    content_type: str = "text"  # "text" or "tool_use" - categorizes content blocks
    response_id: Optional[str] = None  # UUID shared by all blocks in same response

    class Config:
        from_attributes = True


# ============================================================================
# Chat Schemas (Multilingual AI Chat)
# ============================================================================

class ChatMessage(BaseModel):
    """Single chat message."""

    role: str = Field(..., description="Message role: user or assistant")
    content: str = Field(..., description="Message content")
    language: Optional[str] = Field(None, description="Detected language code (vi, en, ja)")
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    """Request to send a chat message."""

    message: str = Field(..., description="User message in any supported language")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    language: Optional[str] = Field(None, description="Force specific language (vi, en, ja)")
    model: Optional[str] = Field("claude-3-5-sonnet-20241022", description="Claude model to use")


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    conversation_id: str
    message: ChatMessage
    detected_language: str = Field(..., description="Auto-detected language code")
    supported_languages: list[str] = Field(default=["vi", "en", "ja"])


class ConversationMetadata(BaseModel):
    """Conversation metadata."""

    conversation_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    primary_language: str = Field(..., description="Primary language used in conversation")


class ConversationHistory(BaseModel):
    """Full conversation history."""

    metadata: ConversationMetadata
    messages: list[ChatMessage]


# ============================================================================
# User Profile Schemas
# ============================================================================

class UserProfileMetadata(BaseModel):
    """User profile data."""

    id: str = "default"  # Singleton record
    avatar: Optional[str] = None
    description: Optional[str] = None
    preferences: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UpdateUserProfileRequest(BaseModel):
    """Request to update user profile."""

    avatar: Optional[str] = None
    description: Optional[str] = None
    preferences: Optional[str] = None
