"""
Specialist session - single character/specialist acting as main agent.

This session type is used when:
- User launches a session with a specific character
- PM spawns a session with a single specialist
"""

import logging
from typing import Dict, Any

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from backend.config.session_roles import SessionRole
from backend.core.constants import (
    STARTUP_CHECKLIST,
    PROJECT_CONTEXT_GUIDELINES,
    CONTACT_PM_GUIDELINES,
    SKILLS_USAGE_GUIDELINE,
    MCP_TOOL_EXECUTION_GUIDELINES,
    REMIND_TOOL_USAGE_GUIDELINES,
    SHOW_FILE_TOOL_GUIDELINES,
)
from backend.sessions.base_session import BaseSession
from backend.services.character_loader import CharacterLoader
from backend.services.mcp_service import MCPServerService
from backend.services.claude_client import kumiAI_tools, common_tools, inject_session_id_hook, normalize_file_path_hook

logger = logging.getLogger(__name__)


class SpecialistSession(BaseSession):
    """
    Session with a single specialist/character as the main agent.

    The specialist gets:
    - Their character content as system prompt (appended to Claude Code preset)
    - Their allowed_tools from capabilities
    - Their MCP servers from allowed_mcp_servers
    - Their custom tools from allowed_custom_tools
    """

    async def _create_claude_options(self) -> ClaudeAgentOptions:
        """
        Create Claude options for specialist session.

        Hybrid loading:
        1. Load capabilities from DATABASE (allowed_tools, allowed_mcp_servers, allowed_skills)
        2. Load content from FILE (agent.md: personality, system prompt)
        3. Load skill descriptions from allowed_skills
        4. Construct final system prompt
        """
        if not self.context.character_id:
            raise ValueError("SpecialistSession requires character_id in context")

        from ..core.database import AsyncSessionLocal
        from ..models.database import Character as DBCharacter
        from ..core.config import settings
        from ..utils.skill_file import SkillFile

        char_loader = CharacterLoader.get_instance()
        mcp_service = MCPServerService.get_instance()

        # 1. Load capabilities from DATABASE
        async with AsyncSessionLocal() as db:
            char_db = await db.get(DBCharacter, self.context.character_id)
            if not char_db:
                raise ValueError(f"Character '{self.context.character_id}' not found in database")

            allowed_tools = (char_db.allowed_tools or []).copy()
            allowed_mcp_servers = char_db.allowed_mcp_servers or []
            allowed_skills = char_db.allowed_skills or []

            # Store character metadata
            self.character_id = self.context.character_id  # Character ID (e.g., "alex")
            self.character_avatar = char_db.avatar or self.context.character_id
            self.character_color = char_db.color or "#4A90E2"

        # 2. Load content from FILE (agent.md)
        character = await char_loader.load_character(self.context.character_id)
        self.character_name = character.name  # Display name (e.g., "Alex")

        logger.info(f"[SPECIALIST_SESSION] Loaded character '{character.name}' ({self.context.character_id})")
        logger.info(f"[SPECIALIST_SESSION] Color: {self.character_color}, Avatar: {self.character_avatar}")

        # Create symlink to character directory
        await char_loader.create_symlink(
            self.context.character_id,
            self.project_path / "agents"
        )

        logger.info(f"[SPECIALIST_SESSION] Character capabilities:")
        logger.info(f"[SPECIALIST_SESSION]   - Base tools: {allowed_tools}")
        logger.info(f"[SPECIALIST_SESSION]   - MCP servers: {allowed_mcp_servers}")

        # Load MCP servers from character capabilities
        # Start with common_tools (available to all sessions)
        mcp_servers = {
            "common_tools": common_tools
        }
        allowed_tools.append("mcp__common_tools")

        logger.info(f"[SPECIALIST_SESSION] ✓ Added common_tools MCP server (contact_pm + remind)")

        if allowed_mcp_servers:
            servers = mcp_service.get_servers_for_character(
                self.context.character_id,
                allowed_mcp_servers
            )
            mcp_servers.update(servers)

            # Add MCP server tools with mcp__ prefix
            for mcp_name in allowed_mcp_servers:
                allowed_tools.append(f"mcp__{mcp_name}")

            logger.info(f"[SPECIALIST_SESSION] ✓ Loaded {len(servers)} character MCP servers: {list(servers.keys())}")

        # 3. Load skill descriptions from allowed_skills (from database)
        skill_descriptions = []
        if allowed_skills:
            logger.info(f"[SPECIALIST_SESSION] Loading {len(allowed_skills)} skill descriptions")

            for skill_id in allowed_skills:
                # Create symlink to skill directory
                skill_path = settings.skills_dir / skill_id
                if skill_path.exists():
                    await char_loader.create_symlink(
                        skill_id,
                        self.project_path / "skills",
                        source_base=settings.skills_dir
                    )

                    # Load skill description
                    skill_file_path = skill_path / "SKILL.md"
                    if skill_file_path.exists():
                        try:
                            skill = await SkillFile.from_file(skill_file_path)
                            skill_descriptions.append(
                                f"## {skill.name}\n{skill.description}\n\n"
                                f"Documentation: See `skills/{skill_id}/SKILL.md`"
                            )
                            logger.info(f"[SPECIALIST_SESSION]   ✓ Loaded skill: {skill.name}")
                        except Exception as e:
                            logger.warning(f"[SPECIALIST_SESSION]   ✗ Failed to load skill {skill_id}: {e}")
                else:
                    logger.warning(f"[SPECIALIST_SESSION]   ✗ Skill path not found: {skill_path}")

        # 4. Build system prompt (character content + skills + shared guidelines)

        # Build skills section from loaded skill descriptions
        skills_section = ""
        if skill_descriptions:
            skills_section = "\n\n# Available Skills\n\nYou have access to the following skill knowledge:\n\n" + "\n\n".join(skill_descriptions)

        # Extract project root and session path
        # Session path format: /project/.sessions/instance_id
        # If session is in .sessions subdirectory, extract project root
        if self.project_path.parent.name == ".sessions":
            project_root = str(self.project_path.parent.parent)
        else:
            project_root = str(self.project_path)

        session_path = str(self.project_path)

        # Combine all shared guidelines
        # Format project context with both project root and session path
        project_context = PROJECT_CONTEXT_GUIDELINES.format(
            project_root=project_root,
            session_path=session_path
        )

        # Build guidelines (conditionally include skills guideline)
        skills_guideline = SKILLS_USAGE_GUIDELINE if skill_descriptions else ""

        guidelines = f"""

{STARTUP_CHECKLIST}

{project_context}

{CONTACT_PM_GUIDELINES}

{skills_guideline}

{MCP_TOOL_EXECUTION_GUIDELINES}

{REMIND_TOOL_USAGE_GUIDELINES}

{SHOW_FILE_TOOL_GUIDELINES}"""

        # Combine all prompt components
        character_prompt = character.content or f"You are {character.name}."
        full_prompt = f"{character_prompt}{skills_section}{guidelines}"

        system_prompt = {
            "type": "preset",
            "preset": "claude_code",
            "append": full_prompt
        }

        logger.info(f"[SPECIALIST_SESSION] ✓ Final configuration:")
        logger.info(f"[SPECIALIST_SESSION]   - Allowed tools: {len(allowed_tools)} tools")
        logger.info(f"[SPECIALIST_SESSION]   - MCP servers: {len(mcp_servers)} servers")
        logger.info(f"[SPECIALIST_SESSION]   - Skills loaded: {len(skill_descriptions)} skills")
        logger.info(f"[SPECIALIST_SESSION]   - System prompt length: {len(full_prompt)} chars")

        # Create Claude options with optional resume
        options_dict = {
            "allowed_tools": allowed_tools,
            "mcp_servers": mcp_servers,
            "system_prompt": system_prompt,
            "model": self.context.get("model", "sonnet"),
            "include_partial_messages": True,
            "cwd": str(self.project_path),
            "permission_mode": "bypassPermissions",  # Skip all permission prompts
            "hooks": {
                "PreToolUse": [
                    HookMatcher(matcher=".*show_file.*", hooks=[normalize_file_path_hook]),
                    HookMatcher(matcher=".*remind.*|.*contact_pm.*|.*contact_session.*", hooks=[inject_session_id_hook])
                ]
            }
        }

        # Add resume parameter if we have an existing session_id
        if self.session_id:
            options_dict["resume"] = self.session_id
            logger.info(f"[SPECIALIST_SESSION] Resuming session: {self.session_id}")

        return ClaudeAgentOptions(**options_dict)
