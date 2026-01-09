"""
Assistant sessions for character/skill editing.

This session type is used for:
- Character assistant (editing agent.md files)
- Skill assistant (editing skill definitions)
"""

import logging
from typing import Dict, Any

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from backend.config.session_roles import SessionRole
from backend.core.constants import MCP_TOOL_EXECUTION_GUIDELINES
from backend.sessions.base_session import BaseSession
from backend.services.claude_client import kumiAI_tools, common_tools, skill_assistant_tools, character_assistant_tools, inject_session_id_hook

logger = logging.getLogger(__name__)


class AssistantSession(BaseSession):
    """
    Assistant session for editing agent/skill configurations.

    Assistants get:
    - File editing tools (specific to their domain)
    - Auto-save detection enabled
    - Simplified prompts focused on their editing task
    """

    async def _create_claude_options(self) -> ClaudeAgentOptions:
        """
        Create Claude options for assistant session.

        Assistants are simple sessions focused on file editing.
        """
        logger.info(f"[ASSISTANT_SESSION] Creating {self.role.value} session")

        # Assistant sessions need file editing tools by default
        allowed_tools = [
            "Read",
            "Write",
            "Edit",
            "Bash",
            "Grep",
            "Glob"
        ]

        # Merge any additional tools from context
        context_tools = self.context.get("allowed_tools", [])
        allowed_tools.extend(context_tools)

        # Start with common_tools (universal)
        mcp_servers = {
            "common_tools": common_tools,
            **self.context.get("character_tools", {})
        }
        allowed_tools.append("mcp__common_tools")

        # Add role-specific MCP servers
        if self.role == SessionRole.SKILL_ASSISTANT:
            mcp_servers["skill_assistant"] = skill_assistant_tools
            allowed_tools.append("mcp__skill_assistant")
            logger.info("[ASSISTANT_SESSION] ✓ Added skill_assistant MCP server")
        elif self.role == SessionRole.CHARACTER_ASSISTANT:
            mcp_servers["character_assistant"] = character_assistant_tools
            allowed_tools.append("mcp__character_assistant")
            logger.info("[ASSISTANT_SESSION] ✓ Added character_assistant MCP server")

        # MCP instructions (shared across all assistant roles)
        mcp_instructions = f"""

{MCP_TOOL_EXECUTION_GUIDELINES}"""

        # Build assistant prompt based on role
        if self.role == SessionRole.CHARACTER_ASSISTANT:
            prompt = f"""You are an AI assistant helping to create or edit agent/character configurations.

Working directory: {self.project_path}

Each character is in its own subdirectory with an agent.md file (e.g., ~/.kumiai/agents/shitara/agent.md).

**IMPORTANT - File Format:**
- Check ~/.kumiai/agents/_template/agent.md for the complete format and structure
- Use YAML frontmatter (skills, color, personality, etc.)
- Follow the markdown template structure
- DO NOT add or modify the "avatar:" field unless explicitly requested - it is auto-generated
- Browse existing characters for examples

Focus on understanding user needs and creating clear, well-structured agent definitions.{mcp_instructions}"""

        elif self.role == SessionRole.SKILL_ASSISTANT:
            prompt = f"""You are a skill assistant helping to create or edit skill definitions.

Working directory: {self.project_path}

Each skill is in its own subdirectory with a skill.md file (e.g., ~/.kumiai/skills/pdf_reader/skill.md).

**IMPORTANT - File Format:**
- Check ~/.kumiai/skills/_template/skill.md for the complete format and structure
- Use YAML frontmatter (name, description, allowed-tools, allowed-mcp-servers, icon, etc.)
- Follow the markdown template structure
- Browse existing skills for examples

Focus on creating modular, reusable skill definitions that can be easily integrated with different characters.{mcp_instructions}"""

        else:
            prompt = f"You are an AI assistant helping with configuration management.{mcp_instructions}"

        logger.info(f"[ASSISTANT_SESSION] ✓ Assistant configuration:")
        logger.info(f"[ASSISTANT_SESSION]   - Role: {self.role.value}")
        logger.info(f"[ASSISTANT_SESSION]   - Tools: {len(allowed_tools)}")

        # Build system prompt
        system_prompt = {
            "type": "preset",
            "preset": "claude_code",
            "append": prompt
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
                    HookMatcher(matcher="remind|contact_pm", hooks=[inject_session_id_hook])
                ]
            }
        }

        # Add resume parameter if we have an existing session_id
        if self.session_id:
            options_dict["resume"] = self.session_id
            logger.info(f"[ASSISTANT_SESSION] Resuming session: {self.session_id}")

        return ClaudeAgentOptions(**options_dict)
