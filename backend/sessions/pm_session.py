"""
PM (Project Manager) session.

This session type is used for project-level orchestration and management.
"""

import logging
from typing import Dict, Any

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from backend.config.session_roles import SessionRole
from backend.core.constants import (
    PM_SYSTEM_PROMPT_TEMPLATE,
    STARTUP_CHECKLIST,
    PROJECT_CONTEXT_GUIDELINES,
    SKILLS_USAGE_GUIDELINE,
    PM_DELEGATION_GUIDELINE,
    MCP_TOOL_EXECUTION_GUIDELINES,
    REMIND_TOOL_USAGE_GUIDELINES,
    SHOW_FILE_TOOL_GUIDELINES,
    NOTIFY_USER_GUIDELINES,
)
from backend.utils.skill_file import SkillFile
from backend.sessions.base_session import BaseSession
from backend.services.character_loader import CharacterLoader
from backend.services.mcp_service import MCPServerService
from backend.services.claude_client import pm_management_tools, kumiAI_tools, common_tools, inject_session_id_hook, normalize_file_path_hook

logger = logging.getLogger(__name__)


class PMSession(BaseSession):
    """
    Project Manager session.

    The PM gets:
    - PM management tools (spawn_instance, get_project_status, etc.)
    - Optional character content if PM has a persona
    - Access to project context
    """

    async def initialize(self) -> str:
        """
        Initialize PM session and ensure Project.pm_instance_id is up to date.

        This override ensures that whenever a PM session is initialized (including
        when it gets renewed due to resume failure), the project's pm_instance_id
        field is updated to track the current PM session.
        """
        # Call parent initialization
        instance_id = await super().initialize()

        # Update Project.pm_instance_id to track this PM session
        await self._update_project_pm_instance_id()

        return instance_id

    async def _update_project_pm_instance_id(self):
        """Update the project's pm_instance_id to point to this PM session."""
        if not self.context.project_id:
            logger.warning(f"[PM_SESSION] No project_id in context, skipping pm_instance_id update")
            return

        from ..core.database import AsyncSessionLocal
        from ..models.database import Project
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(Project).where(Project.id == self.context.project_id)
                )
                project = result.scalar_one_or_none()

                if not project:
                    logger.warning(f"[PM_SESSION] Project {self.context.project_id} not found, cannot update pm_instance_id")
                    return

                # Update pm_instance_id if it's different
                if project.pm_instance_id != self.instance_id:
                    old_instance_id = project.pm_instance_id
                    project.pm_instance_id = self.instance_id
                    await db.commit()
                    logger.info(
                        f"[PM_SESSION] ✓ Updated project {self.context.project_id} "
                        f"pm_instance_id: {old_instance_id} → {self.instance_id}"
                    )
                else:
                    logger.debug(f"[PM_SESSION] Project pm_instance_id already correct: {self.instance_id}")

            except Exception as e:
                logger.error(f"[PM_SESSION] Failed to update project pm_instance_id: {e}", exc_info=True)
                await db.rollback()

    async def _create_claude_options(self) -> ClaudeAgentOptions:
        """
        Create Claude options for PM session.

        PM sessions have access to project management tools.
        """
        logger.info(f"[PM_SESSION] Creating PM session for project: {self.context.project_id}")

        # Load character if specified (PM can have a persona)
        character_content = ""
        if self.context.character_id:
            try:
                char_loader = CharacterLoader.get_instance()
                character = await char_loader.load_character(self.context.character_id)

                self.character_id = self.context.character_id  # Store character ID (e.g., "alex")
                self.character_name = character.name  # Store display name (e.g., "Alex")
                self.character_avatar = character.avatar or self.context.character_id
                self.character_color = character.color

                character_content = character.content or ""

                logger.info(f"[PM_SESSION] Using PM persona: '{character.name}'")

                # Create symlink
                await char_loader.create_symlink(
                    self.context.character_id,
                    self.project_path / "agents"
                )

            except Exception as e:
                logger.warning(f"[PM_SESSION] Failed to load PM character: {e}. Using default PM.")

        # Load skills (PM can access skills for reference)
        skill_descriptions = []
        char_loader = CharacterLoader.get_instance()

        # Get allowed skills from DATABASE (not CharacterFile)
        allowed_skills = []
        if self.context.character_id:
            from backend.core.database import AsyncSessionLocal
            from backend.models.database import Character as DBCharacter

            try:
                async with AsyncSessionLocal() as db:
                    char_db = await db.get(DBCharacter, self.context.character_id)
                    if char_db:
                        allowed_skills = char_db.allowed_skills or []
                        logger.info(f"[PM_SESSION] Found {len(allowed_skills)} skills in database for PM")
                    else:
                        logger.debug(f"[PM_SESSION] PM character not found in database")
            except Exception as e:
                logger.debug(f"[PM_SESSION] Failed to load skills from database: {e}")

        # Load skill descriptions if any skills are defined
        if allowed_skills:
            from backend.core.config import settings

            logger.info(f"[PM_SESSION] Loading {len(allowed_skills)} skill descriptions")

            for skill_id in allowed_skills:
                # Load skill description (PM references skills directly, no symlinks)
                skill_path = settings.skills_dir / skill_id
                if skill_path.exists():
                    # Load skill description
                    skill_file_path = skill_path / "SKILL.md"
                    if skill_file_path.exists():
                        try:
                            skill = await SkillFile.from_file(skill_file_path)
                            # Use full absolute path for PM
                            full_skill_path = str(skill_file_path)
                            skill_descriptions.append(
                                f"## {skill.name}\n\n{skill.description}\n\nDocumentation: `{full_skill_path}`"
                            )
                            logger.info(f"[PM_SESSION]   ✓ Loaded skill: {skill.name}")
                        except Exception as e:
                            logger.warning(f"[PM_SESSION]   ✗ Failed to load skill {skill_id}: {e}")
                else:
                    logger.warning(f"[PM_SESSION]   ✗ Skill path not found: {skill_path}")

        # Build skills section from loaded skill descriptions
        skills_section = ""
        if skill_descriptions:
            skills_section = "\n\n# Available Skills\n\nYou have access to the following skill knowledge:\n\n" + "\n\n".join(skill_descriptions)

        # Extract project root and session path
        # PM session path is typically the project root itself
        # Session path format: /project/.sessions/instance_id (for PM, typically just /project)
        if self.project_path.parent.name == ".sessions":
            project_root = str(self.project_path.parent.parent)
        else:
            project_root = str(self.project_path)

        session_path = str(self.project_path)

        # Build PM prompt from template
        # Format project context with both project root and session path
        project_context = PROJECT_CONTEXT_GUIDELINES.format(
            project_root=project_root,
            session_path=session_path
        )

        pm_prompt = PM_SYSTEM_PROMPT_TEMPLATE.format(
            startup_checklist=STARTUP_CHECKLIST,
            project_context=project_context,
            delegation_guideline=PM_DELEGATION_GUIDELINE,
            skills_section=skills_section,
            skills_usage_guideline=SKILLS_USAGE_GUIDELINE if skills_section else "",
            mcp_guidelines=MCP_TOOL_EXECUTION_GUIDELINES,
            remind_guidelines=REMIND_TOOL_USAGE_GUIDELINES,
            show_file_guidelines=SHOW_FILE_TOOL_GUIDELINES,
            notify_user_guidelines=NOTIFY_USER_GUIDELINES
        )

        # Append character content if available
        if character_content:
            pm_prompt = f"{character_content}\n\n{pm_prompt}"

        # PM gets common tools (universal) + management tools
        mcp_servers = {
            "common_tools": common_tools,
            "pm_management": pm_management_tools
        }

        allowed_tools = ["mcp__common_tools", "mcp__pm_management"]

        logger.info(f"[PM_SESSION] ✓ PM configuration:")
        logger.info(f"[PM_SESSION]   - Tools: {allowed_tools}")
        logger.info(f"[PM_SESSION]   - Project ID: {self.context.project_id}")

        # Build system prompt
        system_prompt = {
            "type": "preset",
            "preset": "claude_code",
            "append": pm_prompt
        }

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
                    HookMatcher(matcher=".*remind.*|.*contact_pm.*|.*pm_management.*contact_session.*|.*notify_user.*", hooks=[inject_session_id_hook])
                ]
            }
        }

        # Add resume parameter if we have an existing session_id
        if self.session_id:
            options_dict["resume"] = self.session_id
            logger.info(f"[PM_SESSION] Resuming session: {self.session_id}")

        return ClaudeAgentOptions(**options_dict)
