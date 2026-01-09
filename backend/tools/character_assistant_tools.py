"""Character Assistant Tools.

These tools enable the character-assistant agent to manage agent configurations,
including setting tools, MCP servers, and skills.
"""
from claude_agent_sdk import tool
from typing import Any
import logging
import json
from sqlalchemy import select

from ..core.database import AsyncSessionLocal
from ..models.database import Character

logger = logging.getLogger(__name__)


def _parse_list_param(value: Any) -> list:
    """Parse a list parameter that might be a JSON string or already a list.

    Args:
        value: The parameter value (list, JSON string, or None)

    Returns:
        Parsed list or empty list if None
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            return []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


@tool(
    "set_agent_tools",
    "Set the allowed tools for an agent. This replaces all existing tools with the provided list.",
    {
        "agent_id": str,
        "tools": list[str]
    }
)
async def set_agent_tools(args: dict[str, Any]) -> dict[str, Any]:
    """Set the allowed tools for an agent.

    This replaces the agent's entire allowed_tools list with the provided tools.

    Args:
        agent_id: The agent ID (e.g., 'elon-981e', 'researcher-a3d5025d')
        tools: List of tool names to allow (e.g., ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep'])

    Available Claude Code tools:
        - Read: Read files
        - Write: Write/create files
        - Edit: Edit existing files
        - Bash: Execute shell commands
        - Glob: Find files by pattern
        - Grep: Search file contents
        - WebFetch: Fetch web content
        - WebSearch: Search the web

    Returns:
        Success or error message
    """
    try:
        agent_id = args.get("agent_id")
        tools = _parse_list_param(args.get("tools"))

        if not agent_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: agent_id is required"
                }]
            }

        async with AsyncSessionLocal() as db:
            # Get or create character database record
            result = await db.execute(
                select(Character).where(Character.id == agent_id)
            )
            db_char = result.scalar_one_or_none()

            if not db_char:
                # Create new database record if doesn't exist
                db_char = Character(
                    id=agent_id,
                    allowed_tools=tools,
                    allowed_mcp_servers=[],
                    allowed_skills=[],
                )
                db.add(db_char)
            else:
                # Update existing record
                db_char.allowed_tools = tools

            await db.commit()

            tools_str = ", ".join(tools) if tools else "None"
            logger.info(f"[CHARACTER_ASSISTANT_TOOLS] Set tools for agent '{agent_id}': {tools_str}")
            return {
                "content": [{
                    "type": "text",
                    "text": f"✓ Successfully set {len(tools)} tool(s) for agent '{agent_id}': {tools_str}"
                }]
            }

    except Exception as e:
        logger.error(f"[CHARACTER_ASSISTANT_TOOLS] Error setting agent tools: {e}")
        return {
            "content": [{
                "type": "text",
                "text": f"Error setting agent tools: {str(e)}"
            }]
        }


@tool(
    "set_agent_mcp_servers",
    "Set the allowed MCP servers for an agent. This replaces all existing MCP servers with the provided list.",
    {
        "agent_id": str,
        "mcp_servers": list[str]
    }
)
async def set_agent_mcp_servers(args: dict[str, Any]) -> dict[str, Any]:
    """Set the allowed MCP servers for an agent.

    This replaces the agent's entire allowed_mcp_servers list with the provided servers.

    Args:
        agent_id: The agent ID (e.g., 'elon-981e', 'researcher-a3d5025d')
        mcp_servers: List of MCP server names to allow (e.g., ['gmail', 'todoist', 'calendar'])

    Available MCP servers vary by installation. Common ones include:
        - gmail: Gmail integration
        - todoist: Todoist task management
        - google-calendar: Google Calendar integration
        - mermaid: Mermaid diagram generation
        - playwright: Browser automation
        - chrome-devtools: Chrome DevTools integration

    Returns:
        Success or error message
    """
    try:
        agent_id = args.get("agent_id")
        mcp_servers = _parse_list_param(args.get("mcp_servers"))

        if not agent_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: agent_id is required"
                }]
            }

        async with AsyncSessionLocal() as db:
            # Get or create character database record
            result = await db.execute(
                select(Character).where(Character.id == agent_id)
            )
            db_char = result.scalar_one_or_none()

            if not db_char:
                # Create new database record if doesn't exist
                db_char = Character(
                    id=agent_id,
                    allowed_tools=[],
                    allowed_mcp_servers=mcp_servers,
                    allowed_skills=[],
                )
                db.add(db_char)
            else:
                # Update existing record
                db_char.allowed_mcp_servers = mcp_servers

            await db.commit()

            servers_str = ", ".join(mcp_servers) if mcp_servers else "None"
            logger.info(f"[CHARACTER_ASSISTANT_TOOLS] Set MCP servers for agent '{agent_id}': {servers_str}")
            return {
                "content": [{
                    "type": "text",
                    "text": f"✓ Successfully set {len(mcp_servers)} MCP server(s) for agent '{agent_id}': {servers_str}"
                }]
            }

    except Exception as e:
        logger.error(f"[CHARACTER_ASSISTANT_TOOLS] Error setting agent MCP servers: {e}")
        return {
            "content": [{
                "type": "text",
                "text": f"Error setting agent MCP servers: {str(e)}"
            }]
        }


@tool(
    "set_agent_skills",
    "Set the allowed skills for an agent. This replaces all existing skills with the provided list.",
    {
        "agent_id": str,
        "skills": list[str]
    }
)
async def set_agent_skills(args: dict[str, Any]) -> dict[str, Any]:
    """Set the allowed skills for an agent.

    This replaces the agent's entire allowed_skills list with the provided skills.

    Args:
        agent_id: The agent ID (e.g., 'elon-981e', 'researcher-a3d5025d')
        skills: List of skill IDs to allow (e.g., ['web-research', 'code-review-excellence'])

    Returns:
        Success or error message
    """
    try:
        agent_id = args.get("agent_id")
        skills = _parse_list_param(args.get("skills"))

        if not agent_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: agent_id is required"
                }]
            }

        async with AsyncSessionLocal() as db:
            # Get or create character database record
            result = await db.execute(
                select(Character).where(Character.id == agent_id)
            )
            db_char = result.scalar_one_or_none()

            if not db_char:
                # Create new database record if doesn't exist
                db_char = Character(
                    id=agent_id,
                    allowed_tools=[],
                    allowed_mcp_servers=[],
                    allowed_skills=skills,
                )
                db.add(db_char)
            else:
                # Update existing record
                db_char.allowed_skills = skills

            await db.commit()

            skills_str = ", ".join(skills) if skills else "None"
            logger.info(f"[CHARACTER_ASSISTANT_TOOLS] Set skills for agent '{agent_id}': {skills_str}")
            return {
                "content": [{
                    "type": "text",
                    "text": f"✓ Successfully set {len(skills)} skill(s) for agent '{agent_id}': {skills_str}"
                }]
            }

    except Exception as e:
        logger.error(f"[CHARACTER_ASSISTANT_TOOLS] Error setting agent skills: {e}")
        return {
            "content": [{
                "type": "text",
                "text": f"Error setting agent skills: {str(e)}"
            }]
        }


@tool(
    "get_agent_capabilities",
    "Get the current capabilities (tools, MCP servers, skills) for an agent.",
    {"agent_id": str}
)
async def get_agent_capabilities(args: dict[str, Any]) -> dict[str, Any]:
    """Get the current capabilities for an agent.

    Args:
        agent_id: The agent ID (e.g., 'elon-981e', 'researcher-a3d5025d')

    Returns:
        Formatted string with agent's current capabilities
    """
    try:
        agent_id = args.get("agent_id")

        if not agent_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: agent_id is required"
                }]
            }

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Character).where(Character.id == agent_id)
            )
            db_char = result.scalar_one_or_none()

            if not db_char:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Agent '{agent_id}' not found in database. No capabilities configured yet."
                    }]
                }

            output = f"# Capabilities for agent '{agent_id}'\n\n"

            # Tools
            tools = db_char.allowed_tools or []
            output += f"**Tools ({len(tools)}):** "
            output += ", ".join(tools) if tools else "None"
            output += "\n\n"

            # MCP Servers
            mcp_servers = db_char.allowed_mcp_servers or []
            output += f"**MCP Servers ({len(mcp_servers)}):** "
            output += ", ".join(mcp_servers) if mcp_servers else "None"
            output += "\n\n"

            # Skills
            skills = db_char.allowed_skills or []
            output += f"**Skills ({len(skills)}):** "
            output += ", ".join(skills) if skills else "None"
            output += "\n"

            return {
                "content": [{
                    "type": "text",
                    "text": output
                }]
            }

    except Exception as e:
        logger.error(f"[CHARACTER_ASSISTANT_TOOLS] Error getting agent capabilities: {e}")
        return {
            "content": [{
                "type": "text",
                "text": f"Error getting agent capabilities: {str(e)}"
            }]
        }


# Tool collection for character-assistant
CHARACTER_ASSISTANT_TOOLS = [
    set_agent_tools,
    set_agent_mcp_servers,
    set_agent_skills,
    get_agent_capabilities,
]
