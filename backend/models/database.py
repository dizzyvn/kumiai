"""SQLAlchemy database models."""
import uuid
from sqlalchemy import Column, String, Integer, JSON, DateTime, ForeignKey, Text, Boolean, Float, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

# Default project ID for non-project sessions
DEFAULT_PROJECT_ID = "default"


class Character(Base):
    """Character configuration model.

    Hybrid storage approach:
    - Database: Structured capabilities (tools, MCP servers, skills)
    - File (agent.md): Free-form content (personality, system prompt)

    Database stores UI-managed capabilities that need to be queryable.
    File stores assistant-editable content that doesn't need structure.
    """

    __tablename__ = "characters"

    id = Column(String, primary_key=True)  # Directory name in ~/.kumiai/agents/

    # Capabilities (UI-managed, structured)
    allowed_tools = Column(JSON, default=list)  # e.g., ["Read", "Write", "Edit", "Bash"]
    allowed_mcp_servers = Column(JSON, default=list)  # e.g., ["gmail", "calendar", "notion"]
    allowed_skills = Column(JSON, default=list)  # e.g., ["productivity/email-management"]

    # UI customization
    avatar = Column(String)  # DiceBear API seed (user can randomize via UI)
    color = Column(String)  # UI color for this character

    # Metadata
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    instances = relationship("AgentInstance", back_populates="character")
    pm_projects = relationship("Project", foreign_keys="Project.pm_id", back_populates="pm_character")


class Project(Base):
    """Project model."""

    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    path = Column(String)  # File system path for the project
    pm_id = Column(String, ForeignKey("characters.id", ondelete="SET NULL"))  # Character assigned as PM
    pm_instance_id = Column(String, ForeignKey("sessions.instance_id", ondelete="SET NULL"), nullable=True)  # Active PM session (NULL if cancelled)
    team_member_ids = Column(JSON)  # List of character IDs available for this project
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    is_archived = Column(Boolean, default=False)

    # Relationships
    pm_character = relationship("Character", foreign_keys=[pm_id], back_populates="pm_projects")
    pm_instance = relationship("AgentInstance", foreign_keys=[pm_instance_id])
    instances = relationship("AgentInstance", foreign_keys="AgentInstance.project_id", back_populates="project", cascade="all, delete-orphan")


class AgentInstance(Base):
    """Active agent session model."""

    __tablename__ = "sessions"

    instance_id = Column(String, primary_key=True)
    character_id = Column(String, ForeignKey("characters.id", ondelete="SET NULL"))
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), default=DEFAULT_PROJECT_ID)
    project_path = Column(String, nullable=False)
    session_description = Column(Text)
    role = Column(String, default="orchestrator")  # orchestrator, pm, specialist
    status = Column(String, default="idle")  # idle, thinking, working, waiting, completed, error
    kanban_stage = Column(String, default="backlog")  # backlog, active, blocked, review, done
    session_id = Column(String)  # Claude SDK session ID
    parent_tool_use_id = Column(String)  # For subagent tracking
    started_at = Column(DateTime, server_default=func.now())
    output_lines = Column(Integer, default=0)
    selected_specialists = Column(JSON)  # Specialist IDs selected for this session (team_member_ids)
    actual_tools = Column(JSON)  # Tools actually used
    actual_mcp_servers = Column(JSON)  # MCP servers used
    actual_skills = Column(JSON)  # Skills invoked
    auto_started = Column(Boolean, default=False)  # Whether session was auto-started in background

    # Relationships
    character = relationship("Character", back_populates="instances")
    project = relationship("Project", foreign_keys=[project_id], back_populates="instances")
    messages = relationship("SessionMessage", back_populates="instance", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="instance", cascade="all, delete-orphan")


class SessionMessage(Base):
    """Conversation messages for chat sessions."""

    __tablename__ = "session_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id = Column(String, ForeignKey("sessions.instance_id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # user, assistant, tool_call, tool_result, system
    content = Column(Text, nullable=False)
    agent_name = Column(String)  # For specialist messages
    tool_name = Column(String)  # For tool_call messages
    tool_args = Column(JSON)  # For tool_call messages (array of {name, id, input})
    tool_use_id = Column(String)  # Claude's tool use ID (for linking tool_call to tool_result)
    is_error = Column(Boolean, default=False)  # For tool_result messages - indicates tool execution failed
    sender_role = Column(String)  # Who sent this message: "user", "pm", "orchestrator"
    sender_id = Column(String)  # Character ID of the sender (e.g., "alex")
    sender_name = Column(String)  # Display name of sender (e.g., "Alex")
    sender_instance = Column(String)  # Session instance ID of the sender (e.g., "pm-0b3ce10b")
    sequence = Column(Integer, default=0)  # Execution order within a response (for ordering tools with text)
    timestamp = Column(DateTime, server_default=func.now())
    cost_usd = Column(Float)  # Track cost per message if available
    content_type = Column(String, default="text")  # "text" or "tool_use" - categorizes content blocks
    response_id = Column(String)  # UUID shared by all blocks in same response

    # Relationships
    instance = relationship("AgentInstance", back_populates="messages")

    __table_args__ = (
        Index('idx_instance_timestamp', 'instance_id', 'timestamp'),
        Index('idx_instance_role', 'instance_id', 'role'),
        Index('idx_instance_content_type', 'instance_id', 'content_type'),
        Index('idx_instance_response_id', 'instance_id', 'response_id'),
    )


class ActivityLog(Base):
    """Agent activity log model."""

    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(String, ForeignKey("sessions.instance_id", ondelete="CASCADE"))
    timestamp = Column(DateTime, server_default=func.now())
    event_type = Column(String)  # agent_started, tool_used, artifact_created, etc.
    data = Column(JSON)

    # Relationships
    instance = relationship("AgentInstance", back_populates="activity_logs")


class Skill(Base):
    """Skill model for storing skill definitions.

    Skills are reusable documentation modules that can be assigned to characters.
    """

    __tablename__ = "skills"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    content = Column(Text)  # Markdown content with skill instructions
    allowed_tools = Column(JSON, default=list)  # Tools required for this skill
    allowed_mcp_servers = Column(JSON, default=list)  # MCP servers required
    allowed_custom_tools = Column(JSON, default=list)  # Custom tools
    icon = Column(String)  # Icon identifier
    icon_color = Column(String)  # Color for the icon
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class UserProfile(Base):
    """User profile model for personalizing AI interactions.

    This is a singleton table - only one record with id='default'.
    The profile information is appended to system prompts when spawning sessions.
    """

    __tablename__ = "user_profile"

    id = Column(String, primary_key=True, default="default")  # Singleton record
    avatar = Column(String)  # Avatar URL or base64 data URI
    description = Column(Text)  # User description (who you are, what you do)
    preferences = Column(Text)  # User preferences (communication style, etc.)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
