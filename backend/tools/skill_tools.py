"""Skill Management Tools.

These tools enable agents to search, list, get, create, and update skills
similar to PM tools and common tools pattern.
"""
from claude_agent_sdk import tool
from typing import Any
import logging
from sqlalchemy import select, or_

from ..core.database import AsyncSessionLocal
from ..models.database import Skill as DBSkill

logger = logging.getLogger(__name__)


@tool(
    "search_skills",
    "Search for skills using partial/fuzzy matching. Searches skill names, descriptions, and IDs.",
    {"query": str}
)
async def search_skills(query: str) -> str:
    """Search for skills with match scoring.

    Args:
        query: Search query (e.g., 'email', 'todo', 'calendar')

    Returns:
        Formatted string with search results and scores
    """
    try:
        async with AsyncSessionLocal() as db:
            # Simple search using LIKE for SQLite compatibility
            stmt = select(DBSkill).where(
                or_(
                    DBSkill.name.ilike(f"%{query}%"),
                    DBSkill.description.ilike(f"%{query}%"),
                    DBSkill.id.ilike(f"%{query}%")
                )
            )
            result = await db.execute(stmt)
            skills = result.scalars().all()

            if not skills:
                return f"No skills found matching '{query}'"

            # Calculate simple match scores
            results = []
            for skill in skills:
                score = 0
                match_field = "description"

                # Exact match in ID = highest score
                if query.lower() in skill.id.lower():
                    score = 100 if query.lower() == skill.id.lower() else 90
                    match_field = "id"
                # Match in name
                elif query.lower() in skill.name.lower():
                    score = 80 if query.lower() == skill.name.lower() else 70
                    match_field = "name"
                # Match in description
                elif query.lower() in (skill.description or "").lower():
                    score = 60
                    match_field = "description"

                results.append({
                    "skill": skill,
                    "score": score,
                    "match_field": match_field
                })

            # Sort by score descending
            results.sort(key=lambda x: x["score"], reverse=True)

            # Format output
            output = f"Found {len(results)} skill(s) matching '{query}':\n\n"

            for i, result in enumerate(results, 1):
                skill = result["skill"]
                score = result["score"]
                match_field = result["match_field"]

                output += f"{i}. **{skill.name}** (ID: `{skill.id}`)\n"
                output += f"   Score: {score}/100 (matched in {match_field})\n"
                output += f"   Description: {skill.description or 'N/A'}\n"
                output += f"   Tools: {', '.join(skill.allowed_tools) if skill.allowed_tools else 'None'}\n"
                output += f"   MCP Servers: {', '.join(skill.allowed_mcp_servers) if skill.allowed_mcp_servers else 'None'}\n\n"

            return output

    except Exception as e:
        logger.error(f"[SKILL_TOOLS] Error searching skills: {e}")
        return f"Error searching skills: {str(e)}"


@tool(
    "list_skills",
    "List all available skills with their metadata",
    {}
)
async def list_skills() -> str:
    """List all skills.

    Returns:
        Formatted string with all skills
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(DBSkill))
            skills = result.scalars().all()

            if not skills:
                return "No skills available"

            output = f"Total skills: {len(skills)}\n\n"

            for skill in skills:
                output += f"• **{skill.name}** (`{skill.id}`)\n"
                output += f"  {skill.description or 'No description'}\n"
                output += f"  Tools: {', '.join(skill.allowed_tools) if skill.allowed_tools else 'None'}\n"
                output += f"  MCP: {', '.join(skill.allowed_mcp_servers) if skill.allowed_mcp_servers else 'None'}\n\n"

            return output

    except Exception as e:
        logger.error(f"[SKILL_TOOLS] Error listing skills: {e}")
        return f"Error listing skills: {str(e)}"


@tool(
    "get_skill",
    "Get detailed information about a specific skill by its ID",
    {"skill_id": str}
)
async def get_skill(skill_id: str) -> str:
    """Get skill details including full content.

    Args:
        skill_id: The skill ID (e.g., 'email-management', 'skill-b3pp2cl6')

    Returns:
        Formatted string with skill details
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBSkill).where(DBSkill.id == skill_id)
            )
            skill = result.scalar_one_or_none()

            if not skill:
                return f"Skill '{skill_id}' not found"

            output = f"# {skill.name}\n\n"
            output += f"**ID:** `{skill.id}`\n"
            output += f"**Description:** {skill.description or 'N/A'}\n\n"

            if skill.allowed_tools:
                output += f"**Allowed Tools:** {', '.join(skill.allowed_tools)}\n"

            if skill.allowed_mcp_servers:
                output += f"**Allowed MCP Servers:** {', '.join(skill.allowed_mcp_servers)}\n"

            if skill.allowed_custom_tools:
                output += f"**Custom Tools:** {', '.join(skill.allowed_custom_tools)}\n"

            output += f"\n## Content\n\n{skill.content or 'No content available'}\n"

            return output

    except Exception as e:
        logger.error(f"[SKILL_TOOLS] Error getting skill: {e}")
        return f"Error getting skill: {str(e)}"


@tool(
    "create_skill",
    "Create a new skill with name, description, content, and capabilities",
    {
        "id": str,
        "name": str,
        "description": str,
        "content": str,
        "allowed_tools": list[str] | None,
        "allowed_mcp_servers": list[str] | None,
        "icon": str | None,
        "icon_color": str | None
    }
)
async def create_skill(
    id: str,
    name: str,
    description: str,
    content: str,
    allowed_tools: list[str] | None = None,
    allowed_mcp_servers: list[str] | None = None,
    icon: str | None = None,
    icon_color: str | None = None
) -> str:
    """Create a new skill.

    Args:
        id: Unique skill ID (e.g., 'my-new-skill')
        name: Display name for the skill
        description: Brief description of what the skill does
        content: Markdown content with instructions and implementation details
        allowed_tools: List of allowed Claude Code tools (e.g., ['Read', 'Write', 'Bash'])
        allowed_mcp_servers: List of allowed MCP servers (e.g., ['gmail', 'todoist'])
        icon: Icon name (optional)
        icon_color: Icon color hex code (optional, e.g., '#8B5CF6')

    Returns:
        Success or error message
    """
    try:
        async with AsyncSessionLocal() as db:
            # Check if skill already exists
            existing = await db.execute(
                select(DBSkill).where(DBSkill.id == id)
            )
            if existing.scalar_one_or_none():
                return f"Error: Skill with ID '{id}' already exists"

            skill = DBSkill(
                id=id,
                name=name,
                description=description,
                content=content,
                allowed_tools=allowed_tools or [],
                allowed_mcp_servers=allowed_mcp_servers or [],
                icon=icon,
                icon_color=icon_color
            )

            db.add(skill)
            await db.commit()

            logger.info(f"[SKILL_TOOLS] Created skill: {id}")
            return f"✓ Skill '{name}' created successfully with ID: {id}"

    except Exception as e:
        logger.error(f"[SKILL_TOOLS] Error creating skill: {e}")
        return f"Error creating skill: {str(e)}"


@tool(
    "update_skill",
    "Update an existing skill's properties",
    {
        "skill_id": str,
        "name": str | None,
        "description": str | None,
        "content": str | None,
        "allowed_tools": list[str] | None,
        "allowed_mcp_servers": list[str] | None,
        "icon": str | None,
        "icon_color": str | None
    }
)
async def update_skill(
    skill_id: str,
    name: str | None = None,
    description: str | None = None,
    content: str | None = None,
    allowed_tools: list[str] | None = None,
    allowed_mcp_servers: list[str] | None = None,
    icon: str | None = None,
    icon_color: str | None = None
) -> str:
    """Update an existing skill.

    Args:
        skill_id: The skill ID to update
        name: New name (optional)
        description: New description (optional)
        content: New content (optional)
        allowed_tools: New allowed tools list (optional)
        allowed_mcp_servers: New allowed MCP servers list (optional)
        icon: New icon (optional)
        icon_color: New icon color (optional)

    Returns:
        Success or error message
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBSkill).where(DBSkill.id == skill_id)
            )
            skill = result.scalar_one_or_none()

            if not skill:
                return f"Skill '{skill_id}' not found"

            # Update only provided fields
            if name is not None:
                skill.name = name
            if description is not None:
                skill.description = description
            if content is not None:
                skill.content = content
            if allowed_tools is not None:
                skill.allowed_tools = allowed_tools
            if allowed_mcp_servers is not None:
                skill.allowed_mcp_servers = allowed_mcp_servers
            if icon is not None:
                skill.icon = icon
            if icon_color is not None:
                skill.icon_color = icon_color

            await db.commit()

            logger.info(f"[SKILL_TOOLS] Updated skill: {skill_id}")
            return f"✓ Skill '{skill.name}' updated successfully"

    except Exception as e:
        logger.error(f"[SKILL_TOOLS] Error updating skill: {e}")
        return f"Error updating skill: {str(e)}"
