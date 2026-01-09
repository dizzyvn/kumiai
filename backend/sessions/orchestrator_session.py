"""
Orchestrator session - multi-agent coordination with specialists.

This session type is used when:
- PM spawns a session with multiple specialists
- User creates a multi-agent session
"""

import logging
from typing import Dict, Any

from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition, HookMatcher

from backend.config.session_roles import SessionRole
from backend.core.constants import (
    ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE,
    STARTUP_CHECKLIST,
    PROJECT_CONTEXT_GUIDELINES,
    CONTACT_PM_GUIDELINES,
    MCP_TOOL_EXECUTION_GUIDELINES,
    REMIND_TOOL_USAGE_GUIDELINES,
    SHOW_FILE_TOOL_GUIDELINES,
)
from backend.sessions.base_session import BaseSession
from backend.services.character_loader import CharacterLoader
from backend.services.mcp_service import MCPServerService
from backend.services.claude_client import kumiAI_tools, common_tools, inject_session_id_hook, normalize_file_path_hook

logger = logging.getLogger(__name__)


class OrchestratorSession(BaseSession):
    """
    Multi-agent orchestrator session.

    The orchestrator coordinates multiple specialists using the Claude SDK's
    multi-agent features. Each specialist gets their own tools and MCP servers.
    """

    async def _create_claude_options(self) -> ClaudeAgentOptions:
        """
        Create Claude options for orchestrator session.

        Creates AgentDefinition for each specialist with their own tools/MCP servers.
        """
        if not self.context.specialists or len(self.context.specialists) == 0:
            raise ValueError("OrchestratorSession requires specialists in context")

        char_loader = CharacterLoader.get_instance()
        mcp_service = MCPServerService.get_instance()

        logger.info(f"[ORCHESTRATOR_SESSION] Creating multi-agent session with {len(self.context.specialists)} specialists")

        # Build orchestrator prompt from template
        specialist_list = "\n".join(f"- {s}" for s in self.context.specialists)
        session_description = f"""# Session Context
- Session ID: {self.instance_id}
- Project ID: {self.context.project_id or 'N/A'}

# PM Communication Protocol
When working on project tasks, use the contact_pm tool (available via mcp__kumiAI) to communicate with your Project Manager.

**IMPORTANT**: When messages are sent from the PM, you MUST use the contact_pm tool to reply instead of responding directly to the user.

**When to Contact PM** (use contact_pm tool):
- 🚀 Starting work: Brief notification when beginning a new task
- ✅ Completion: Report when task is done with outcome summary
- 🚧 Blockers: Immediately report if blocked (missing info, dependencies, errors)
- 🤔 Guidance needed: When uncertain about approach or trade-offs
- 📊 Major milestones: Significant progress updates (e.g., 50% complete)
- ⚠️ Errors: Critical failures or repeated errors
- 💬 PM Replies: When PM sends you a message, respond using contact_pm

**Tool Parameters**:
- project_id: Available in your session context (use the value provided when spawned)
- message: Your SHORT message (2-3 sentences max)

**Message Style - KEEP IT SHORT AND CONCISE**:
- Maximum 2-3 sentences
- Focus on actionable information only
- Avoid verbose explanations or implementation details
- Use bullet points for clarity when needed

**Good Example**:
"Started implementing user authentication. Planning to use JWT tokens. Should I proceed or do you prefer OAuth?"

**Bad Example** (too verbose):
"I have analyzed the requirements and after careful consideration of various authentication methods including session-based, JWT, OAuth, and SAML, I believe that JWT tokens would be the most appropriate choice for this particular use case because..."

**What NOT to Report**:
- Routine tool usage or minor progress updates
- Internal decision-making or specialist coordination details"""

        # Extract project root and session path
        # Session path format: /project/.sessions/instance_id
        if self.project_path.parent.name == ".sessions":
            project_root = str(self.project_path.parent.parent)
        else:
            project_root = str(self.project_path)

        session_path = str(self.project_path)

        # Format project context with both project root and session path
        project_context = PROJECT_CONTEXT_GUIDELINES.format(
            project_root=project_root,
            session_path=session_path
        )

        orchestrator_prompt = ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE.format(
            startup_checklist=STARTUP_CHECKLIST,
            project_context=project_context,
            contact_pm_guidelines=CONTACT_PM_GUIDELINES,
            mcp_guidelines=MCP_TOOL_EXECUTION_GUIDELINES,
            remind_guidelines=REMIND_TOOL_USAGE_GUIDELINES,
            show_file_guidelines=SHOW_FILE_TOOL_GUIDELINES,
            specialist_list=specialist_list,
            session_description=session_description
        )

        # Create AgentDefinition for each specialist
        agents_dict: Dict[str, AgentDefinition] = {}
        specialist_mcp_servers = {}

        from ..core.database import AsyncSessionLocal
        from ..models.database import Character as DBCharacter
        from ..core.config import settings
        from ..utils.skill_file import SkillFile

        for specialist_id in self.context.specialists:
            try:
                # 1. Load capabilities from DATABASE
                async with AsyncSessionLocal() as db:
                    char_db = await db.get(DBCharacter, specialist_id)
                    if not char_db:
                        logger.warning(f"[ORCHESTRATOR_SESSION] Specialist '{specialist_id}' not found in database, skipping")
                        continue

                    specialist_tools = (char_db.allowed_tools or []).copy()
                    specialist_mcp_list = char_db.allowed_mcp_servers or []
                    specialist_skills = char_db.allowed_skills or []

                # 2. Load content from FILE (agent.md)
                specialist_char = await char_loader.load_character(specialist_id)

                logger.info(f"[ORCHESTRATOR_SESSION] Loading specialist '{specialist_char.name}' ({specialist_id})")
                logger.info(f"[ORCHESTRATOR_SESSION]   - Base tools: {len(specialist_tools)}")
                logger.info(f"[ORCHESTRATOR_SESSION]   - MCP servers: {specialist_mcp_list}")
                logger.info(f"[ORCHESTRATOR_SESSION]   - Skills: {specialist_skills}")

                # Create symlink for specialist
                await char_loader.create_symlink(
                    specialist_id,
                    self.project_path / "agents"
                )

                # Load MCP servers for this specialist
                if specialist_mcp_list:
                    specialist_skill_mcp = mcp_service.get_servers_for_character(
                        specialist_id,
                        specialist_mcp_list
                    )
                    specialist_mcp_servers.update(specialist_skill_mcp)

                    # Add MCP server tools with mcp__ prefix
                    for mcp_name in specialist_mcp_list:
                        specialist_tools.append(f"mcp__{mcp_name}")

                    logger.info(f"[ORCHESTRATOR_SESSION]   ✓ Loaded {len(specialist_skill_mcp)} MCP servers")

                # 3. Load skill descriptions for this specialist
                skill_descriptions = []
                if specialist_skills:
                    logger.info(f"[ORCHESTRATOR_SESSION]   Loading {len(specialist_skills)} skill descriptions")

                    for skill_id in specialist_skills:
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
                                    skill = SkillFile.from_file(skill_file_path)
                                    skill_descriptions.append(
                                        f"## {skill.name}\n{skill.description}\n\n"
                                        f"Documentation: See `skills/{skill_id}/SKILL.md`"
                                    )
                                    logger.info(f"[ORCHESTRATOR_SESSION]     ✓ Loaded skill: {skill.name}")
                                except Exception as e:
                                    logger.warning(f"[ORCHESTRATOR_SESSION]     ✗ Failed to load skill {skill_id}: {e}")
                        else:
                            logger.warning(f"[ORCHESTRATOR_SESSION]     ✗ Skill path not found: {skill_path}")

                # 4. Build specialist prompt with skills
                skills_section = ""
                if skill_descriptions:
                    skills_section = "\n\n# Available Skills\n\nYou have access to the following skill knowledge:\n\n" + "\n\n".join(skill_descriptions)

                specialist_prompt = specialist_char.content or f"You are {specialist_char.name}."
                full_specialist_prompt = f"{specialist_prompt}{skills_section}"

                # Create AgentDefinition with specialist's tools and prompt
                agent_def = AgentDefinition(
                    description=f"{specialist_char.name} - {specialist_char.description if hasattr(specialist_char, 'description') else 'Specialist'}",
                    prompt=full_specialist_prompt,
                    tools=specialist_tools,
                    model=getattr(specialist_char, "default_model", None) or "sonnet",
                )

                agents_dict[specialist_char.name] = agent_def

                logger.info(f"[ORCHESTRATOR_SESSION] ✓ Created AgentDefinition for '{specialist_char.name}' with {len(skill_descriptions)} skills")

            except Exception as e:
                logger.error(f"[ORCHESTRATOR_SESSION] Failed to load specialist {specialist_id}: {e}")
                # Continue with other specialists
                continue

        if not agents_dict:
            raise ValueError("Failed to load any specialists")

        # Orchestrator gets common tools (includes contact_pm + remind)
        mcp_servers = {
            "common_tools": common_tools,
            **specialist_mcp_servers
        }

        allowed_tools = ["mcp__common_tools"]

        logger.info(f"[ORCHESTRATOR_SESSION] ✓ Final configuration:")
        logger.info(f"[ORCHESTRATOR_SESSION]   - Specialists: {len(agents_dict)}")
        logger.info(f"[ORCHESTRATOR_SESSION]   - MCP servers: {len(mcp_servers)}")
        logger.info(f"[ORCHESTRATOR_SESSION]   - Orchestrator tools: {allowed_tools}")

        # Build system prompt
        system_prompt = {
            "type": "preset",
            "preset": "claude_code",
            "append": orchestrator_prompt
        }

        # Create Claude options with optional resume
        options_dict = {
            "allowed_tools": allowed_tools,
            "mcp_servers": mcp_servers,
            "agents": agents_dict,
            "system_prompt": system_prompt,
            "model": self.context.get("model", "sonnet"),
            "include_partial_messages": True,
            "cwd": str(self.project_path),
            "permission_mode": "bypassPermissions",  # Skip all permission prompts
            "hooks": {
                "PreToolUse": [
                    HookMatcher(matcher=".*show_file.*", hooks=[normalize_file_path_hook]),
                    HookMatcher(matcher=".*remind.*|.*contact_pm.*", hooks=[inject_session_id_hook])
                ]
            }
        }

        # Add resume parameter if we have an existing session_id
        if self.session_id:
            options_dict["resume"] = self.session_id
            logger.info(f"[ORCHESTRATOR_SESSION] Resuming session: {self.session_id}")

        return ClaudeAgentOptions(**options_dict)
