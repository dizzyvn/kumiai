"""
Session role configuration system.

Defines configuration for each session type (role) including:
- System prompts
- Allowed tools and MCP servers
- Message filtering rules
- Auto-save behavior
- UI rendering hints
"""

import logging
from enum import Enum
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class SessionRole(str, Enum):
    """Session role types."""
    ORCHESTRATOR = "orchestrator"
    PM = "pm"
    SINGLE_SPECIALIST = "single_specialist"  # Single agent acting as main agent (not via orchestrator)
    CHARACTER_ASSISTANT = "character_assistant"  # AI assistant for creating/editing character configs
    SKILL_ASSISTANT = "skill_assistant"  # AI assistant for creating/editing skill configs


@dataclass
class MessageFilterConfig:
    """Configuration for message filtering in UI."""
    # Which message roles to show in UI (user, assistant, tool)
    show_roles: List[str]
    # Only show messages from specific agent names (None = show all)
    show_agent_names_only: Optional[List[str]]
    # Hide orchestrator messages (for specialist-only view)
    hide_orchestrator: bool


@dataclass
class RoleConfig:
    """Configuration for a specific session role."""
    role: SessionRole
    # System prompt template (can include placeholders)
    system_prompt_template: str
    # Function to get MCP servers for this role
    get_mcp_servers: Callable[[Dict[str, Any]], Dict[str, Any]]
    # Function to get allowed tools for this role
    get_allowed_tools: Callable[[Dict[str, Any]], List[str]]
    # Message filtering configuration for UI
    message_filter: MessageFilterConfig
    # Whether to auto-save content (for assistants)
    auto_save: bool
    # Auto-save file type (skill, character, etc.)
    auto_save_type: Optional[str]
    # Whether session supports specialists
    supports_specialists: bool
    # Display name for UI
    display_name: str
    # Icon identifier for UI
    icon: str


# System prompt for orchestrator
ORCHESTRATOR_PROMPT = """You are a team orchestrator managing a group of specialist agents.

Your team members are:
{specialists}

Use the call_agent tool to delegate tasks to appropriate specialists based on their expertise.
You can coordinate multiple specialists to complete complex tasks.

Available tools: {tools}
"""

# System prompt for PM
PM_PROMPT = """You are a Project Manager AI assistant.

You have access to the following project management tools:
- spawn_instance: Create new work instances for project tasks
- get_project_status: View all instances and their stages
- update_instance_stage: Move instances through workflow stages
- contact_session: Communicate with active sessions
- list_team_members: View available specialists

Project context is available in PROJECT.md in the session directory.

Your communication style should be:
- Brief and action-focused
- Clear about dependencies and blockers
- Proactive in identifying next steps

When managing dependent tasks:
1. Spawn sessions in dependency order
2. Monitor progress via get_project_status
3. Coordinate handoffs between sessions
"""

# System prompt for single specialist (character acting as main agent)
SINGLE_SPECIALIST_PROMPT = """You are an AI assistant with specialized capabilities.

Your character profile and skills are defined in your configuration.

Available tools: {tools}
"""

# System prompt for character assistant (for editing agent configs)
CHARACTER_ASSISTANT_PROMPT = """You are an AI assistant helping to create or edit agent/character configurations.

Agents are stored in ~/.kumiai/agents/ directory. Each agent is defined in an agent.md file with YAML
frontmatter and markdown content. Your job is to help users create or modify agent configurations based
on their requirements.

IMPORTANT: See ~/.kumiai/agents/_template/ for the correct file format and examples. Always use YAML
frontmatter format. DO NOT add or modify the "avatar:" field unless the user explicitly asks - it is auto-generated.

Available tools: {tools}
"""

# System prompt for skill assistant
SKILL_ASSISTANT_PROMPT = """You are a skill assistant helping to create or edit a skill definition.

Skills are stored in ~/.kumiai/skills/ directory. Each skill is defined in a skill.md file with YAML
frontmatter and markdown content. Skills are reusable capabilities that can be assigned to AI agents.
Your job is to help define the skill's purpose, tools, and instructions based on user requirements.

IMPORTANT: See ~/.kumiai/skills/_template/ for the correct file format and examples.

Available tools: {tools}
"""



def get_orchestrator_mcp_servers(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get MCP servers for orchestrator role."""
    from backend.services.claude_client import kumiAI_tools

    servers = {"kumiAI": kumiAI_tools}

    # Add character-specific tools if available
    if context.get("character_tools"):
        servers["character_tools"] = context["character_tools"]

    return servers


def get_pm_mcp_servers(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get MCP servers for PM role."""
    from backend.services.claude_client import pm_management_tools

    return {"pm_management": pm_management_tools}




def get_orchestrator_allowed_tools(context: Dict[str, Any]) -> List[str]:
    """Get allowed tools for orchestrator role."""
    # Orchestrator gets character-specific allowed tools + kumiAI tools
    tools = context.get("allowed_tools", []).copy()

    # Add kumiAI MCP tools (includes contact_pm)
    tools.append("mcp__kumiAI")

    return tools


def get_pm_allowed_tools(context: Dict[str, Any]) -> List[str]:
    """Get allowed tools for PM role."""
    # PM needs MCP tools explicitly enabled
    # Format: mcp__<server_name> enables all tools from that MCP server
    return ["mcp__pm_management"]


def get_single_specialist_mcp_servers(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get MCP servers for single specialist role."""
    from backend.services.mcp_service import MCPServerService

    servers = {}

    # Load MCP servers from character capabilities
    character_capabilities = context.get("character_capabilities", {})
    allowed_mcp_servers = character_capabilities.get("allowed_mcp_servers", [])
    character_id = context.get("character_id", "unknown")

    if allowed_mcp_servers:
        mcp_service = MCPServerService.get_instance()
        servers = mcp_service.get_servers_for_character(character_id, allowed_mcp_servers)
        logger.debug(f"[ROLE_CONFIG] Loaded {len(servers)} MCP servers for single_specialist: {list(servers.keys())}")

    # Add character-specific tools if available
    if context.get("character_tools"):
        servers.update(context["character_tools"])

    return servers


def get_single_specialist_allowed_tools(context: Dict[str, Any]) -> List[str]:
    """Get allowed tools for single specialist role."""
    # Get tools from character capabilities
    character_capabilities = context.get("character_capabilities", {})
    allowed_tools = character_capabilities.get("allowed_tools", []).copy()
    allowed_mcp_servers = character_capabilities.get("allowed_mcp_servers", [])

    # Add MCP server tools with mcp__ prefix
    for mcp_name in allowed_mcp_servers:
        allowed_tools.append(f"mcp__{mcp_name}")

    logger.debug(f"[ROLE_CONFIG] Allowed tools for single_specialist: {len(allowed_tools)} tools")
    logger.debug(f"[ROLE_CONFIG]   - Base tools: {character_capabilities.get('allowed_tools', [])}")
    logger.debug(f"[ROLE_CONFIG]   - MCP tools added: {[f'mcp__{m}' for m in allowed_mcp_servers]}")

    return allowed_tools


def get_character_assistant_mcp_servers(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get MCP servers for character assistant role (for editing agent configs)."""
    from backend.services.claude_client import character_assistant_tools

    servers = {"character_assistant": character_assistant_tools}

    # Character assistant gets file editing tools if available
    if context.get("character_tools"):
        servers["character_tools"] = context["character_tools"]

    return servers


def get_character_assistant_allowed_tools(context: Dict[str, Any]) -> List[str]:
    """Get allowed tools for character assistant role (for editing agent configs)."""
    # Character assistant gets character-specific allowed tools + character_assistant MCP tools
    tools = context.get("allowed_tools", []).copy()
    tools.append("mcp__character_assistant")
    return tools


def get_skill_assistant_mcp_servers(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get MCP servers for skill assistant role."""
    servers = {}

    # Add skill-specific tools if available
    if context.get("skill_tools"):
        servers["skill_tools"] = context["skill_tools"]

    return servers


def get_skill_assistant_allowed_tools(context: Dict[str, Any]) -> List[str]:
    """Get allowed tools for skill assistant role."""
    # Skill assistant gets skill-specific allowed tools
    return context.get("allowed_tools", [])




# Role configuration registry
ROLE_CONFIGS: Dict[SessionRole, RoleConfig] = {
    SessionRole.ORCHESTRATOR: RoleConfig(
        role=SessionRole.ORCHESTRATOR,
        system_prompt_template=ORCHESTRATOR_PROMPT,
        get_mcp_servers=get_orchestrator_mcp_servers,
        get_allowed_tools=get_orchestrator_allowed_tools,
        message_filter=MessageFilterConfig(
            show_roles=["user", "assistant"],
            show_agent_names_only=None,  # Show all agents (specialists)
            hide_orchestrator=True,  # Hide orchestrator messages
        ),
        auto_save=False,
        auto_save_type=None,
        supports_specialists=True,
        display_name="Orchestrator",
        icon="users",
    ),
    SessionRole.PM: RoleConfig(
        role=SessionRole.PM,
        system_prompt_template=PM_PROMPT,
        get_mcp_servers=get_pm_mcp_servers,
        get_allowed_tools=get_pm_allowed_tools,
        message_filter=MessageFilterConfig(
            show_roles=["user", "assistant"],
            show_agent_names_only=None,  # Show all messages
            hide_orchestrator=False,  # Show PM messages
        ),
        auto_save=False,
        auto_save_type=None,
        supports_specialists=False,
        display_name="Project Manager",
        icon="briefcase",
    ),
    SessionRole.SINGLE_SPECIALIST: RoleConfig(
        role=SessionRole.SINGLE_SPECIALIST,
        system_prompt_template=SINGLE_SPECIALIST_PROMPT,
        get_mcp_servers=get_single_specialist_mcp_servers,
        get_allowed_tools=get_single_specialist_allowed_tools,
        message_filter=MessageFilterConfig(
            show_roles=["user", "assistant"],
            show_agent_names_only=None,  # Show all messages
            hide_orchestrator=False,  # Show specialist messages
        ),
        auto_save=False,
        auto_save_type=None,
        supports_specialists=False,
        display_name="Specialist",
        icon="user",
    ),
    SessionRole.CHARACTER_ASSISTANT: RoleConfig(
        role=SessionRole.CHARACTER_ASSISTANT,
        system_prompt_template=CHARACTER_ASSISTANT_PROMPT,
        get_mcp_servers=get_character_assistant_mcp_servers,
        get_allowed_tools=get_character_assistant_allowed_tools,
        message_filter=MessageFilterConfig(
            show_roles=["user", "assistant"],
            show_agent_names_only=None,  # Show all messages
            hide_orchestrator=False,  # Show assistant messages
        ),
        auto_save=False,
        auto_save_type=None,
        supports_specialists=False,
        display_name="Agent Editor",
        icon="edit",
    ),
    SessionRole.SKILL_ASSISTANT: RoleConfig(
        role=SessionRole.SKILL_ASSISTANT,
        system_prompt_template=SKILL_ASSISTANT_PROMPT,
        get_mcp_servers=get_skill_assistant_mcp_servers,
        get_allowed_tools=get_skill_assistant_allowed_tools,
        message_filter=MessageFilterConfig(
            show_roles=["user", "assistant"],
            show_agent_names_only=None,  # Show all messages
            hide_orchestrator=False,  # Show skill assistant messages
        ),
        auto_save=False,
        auto_save_type=None,
        supports_specialists=False,
        display_name="Skill Assistant",
        icon="wrench",
    ),
}


def get_role_config(role: SessionRole) -> RoleConfig:
    """Get configuration for a specific role."""
    return ROLE_CONFIGS[role]


async def format_system_prompt(role: SessionRole, context: Dict[str, Any]) -> str:
    """Format system prompt template with context variables.

    For PM, orchestrator, and single_specialist roles with a character_id, prepends the character's
    content from agent.md file before the default template.

    For skill_assistant role with a skill_id, prepends the skill's content from skill.md file.

    User profile information (if available) is appended at the end to personalize interactions.
    """
    config = get_role_config(role)
    template = config.system_prompt_template
    character_prefix = ""
    user_profile_suffix = ""

    # For PM, orchestrator, and single_specialist with character_id, prepend character's content
    if role in (SessionRole.PM, SessionRole.ORCHESTRATOR, SessionRole.SINGLE_SPECIALIST) and context.get("character_id"):
        from backend.utils.character_file import load_character_from_file

        character_id = context["character_id"]
        logger.debug(f"[SYSTEM_PROMPT] Loading character content for {role.value} with character_id: {character_id}")
        try:
            character = await load_character_from_file(character_id)
            if character and character.content:
                # Prepend character's markdown content before default template
                character_prefix = character.content
                logger.debug(f"[SYSTEM_PROMPT] Prepending character content (length: {len(character_prefix)} chars)")
                logger.debug(f"[SYSTEM_PROMPT] First 200 chars: {character_prefix[:200]}...")
            else:
                logger.debug(f"[SYSTEM_PROMPT] Character has no content, using default template only")
        except Exception as e:
            # Continue with default template on error
            logger.debug(f"[SYSTEM_PROMPT] Failed to load character {character_id}: {e}, using default template only")
    # For skill_assistant with skill_id, prepend skill's content
    elif role == SessionRole.SKILL_ASSISTANT and context.get("skill_id"):
        from backend.utils.skill_file import load_skill_from_file

        skill_id = context["skill_id"]
        logger.debug(f"[SYSTEM_PROMPT] Loading skill content for {role.value} with skill_id: {skill_id}")
        try:
            skill = await load_skill_from_file(skill_id)
            if skill and skill.content:
                # Prepend skill's markdown content before default template
                character_prefix = skill.content
                logger.debug(f"[SYSTEM_PROMPT] Prepending skill content (length: {len(character_prefix)} chars)")
                logger.debug(f"[SYSTEM_PROMPT] First 200 chars: {character_prefix[:200]}...")
            else:
                logger.debug(f"[SYSTEM_PROMPT] Skill has no content, using default template only")
        except Exception as e:
            # Continue with default template on error
            logger.debug(f"[SYSTEM_PROMPT] Failed to load skill {skill_id}: {e}, using default template only")

    # Replace placeholders with context values in the default template
    if "{specialists}" in template:
        specialists = context.get("specialists", [])
        specialists_str = "\n".join(f"- {s}" for s in specialists)
        template = template.replace("{specialists}", specialists_str)

    if "{tools}" in template:
        tools = context.get("tools", [])
        tools_str = ", ".join(tools)
        template = template.replace("{tools}", tools_str)

    # Load user profile and append to system prompt
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.models.database import UserProfile
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserProfile).where(UserProfile.id == "default")
            )
            user_profile = result.scalar_one_or_none()

            if user_profile:
                profile_parts = []

                if user_profile.description:
                    profile_parts.append(f"**About the user:**\n{user_profile.description}")

                if user_profile.preferences:
                    profile_parts.append(f"**User preferences:**\n{user_profile.preferences}")

                if profile_parts:
                    user_profile_suffix = "\n\n---\n\n" + "\n\n".join(profile_parts)
                    logger.debug(f"[SYSTEM_PROMPT] Appending user profile (length: {len(user_profile_suffix)} chars)")
    except Exception as e:
        # Continue without user profile on error
        logger.debug(f"[SYSTEM_PROMPT] Failed to load user profile: {e}, continuing without it")

    # Combine: character content + default template + user profile
    if character_prefix and user_profile_suffix:
        final_prompt = f"{character_prefix}\n\n---\n\n{template}{user_profile_suffix}"
        logger.debug(f"[SYSTEM_PROMPT] Final prompt length: {len(final_prompt)} chars (character: {len(character_prefix)}, default: {len(template)}, profile: {len(user_profile_suffix)})")
    elif character_prefix:
        final_prompt = f"{character_prefix}\n\n---\n\n{template}{user_profile_suffix}"
        logger.debug(f"[SYSTEM_PROMPT] Final prompt length: {len(final_prompt)} chars (character: {len(character_prefix)}, default: {len(template)}, profile: {len(user_profile_suffix)})")
    elif user_profile_suffix:
        final_prompt = f"{template}{user_profile_suffix}"
        logger.debug(f"[SYSTEM_PROMPT] Final prompt length: {len(final_prompt)} chars (default: {len(template)}, profile: {len(user_profile_suffix)})")
    else:
        final_prompt = template
        logger.debug(f"[SYSTEM_PROMPT] Final prompt length: {len(final_prompt)} chars (default only)")

    return final_prompt
