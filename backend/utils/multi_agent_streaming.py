"""
Production-ready multi-agent streaming following Test 47 architecture.

Key principles:
- Agents load from .claude/agents/{name}/agent.md
- Independent sessions with resumption
- Explicit context passing
- Real-time streaming via async queue
- No Task tool - direct agent invocation
"""
import asyncio
import logging
from typing import Any, Optional
from pathlib import Path
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,
    AssistantMessage,
    SystemMessage,
    TextBlock,
    tool,
    create_sdk_mcp_server,
)
from claude_agent_sdk.types import StreamEvent

logger = logging.getLogger(__name__)


class AgentSessionManager:
    """Manages independent specialist agent sessions with resumption."""

    def __init__(self):
        self.sessions: dict[str, str] = {}  # agent_name -> session_id
        # Separate queue per orchestrator session
        self.message_queues: dict[str, asyncio.Queue] = {}  # orchestrator_session_id -> queue
        self._db_loaded = False  # Track if we've loaded sessions from database

    def get_queue(self, orchestrator_session_id: str) -> asyncio.Queue:
        """Get or create queue for a specific orchestrator session."""
        if orchestrator_session_id not in self.message_queues:
            self.message_queues[orchestrator_session_id] = asyncio.Queue()
        return self.message_queues[orchestrator_session_id]

    async def put_message(self, orchestrator_session_id: str, message: dict):
        """Add a message to the orchestrator's streaming queue."""
        queue = self.get_queue(orchestrator_session_id)
        await queue.put(message)

    async def get_message(self, orchestrator_session_id: str) -> Optional[dict]:
        """Get next message from orchestrator's queue (non-blocking)."""
        queue = self.get_queue(orchestrator_session_id)
        try:
            return await asyncio.wait_for(queue.get(), timeout=0.01)
        except asyncio.TimeoutError:
            return None

    def cleanup_queue(self, orchestrator_session_id: str):
        """Clean up queue when orchestrator session ends."""
        if orchestrator_session_id in self.message_queues:
            del self.message_queues[orchestrator_session_id]
            print(f"[QUEUE] Cleaned up queue for session {orchestrator_session_id}")

    async def _load_sessions_from_db(self):
        """Load specialist sessions from database on first access."""
        if self._db_loaded:
            return

        try:
            from ..core.database import AsyncSessionLocal
            from ..models.database import AgentInstance as DBAgentInstance
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                # Load all specialist sessions with valid session_ids
                result = await db.execute(
                    select(DBAgentInstance).where(
                        DBAgentInstance.role == "specialist",
                        DBAgentInstance.session_id.isnot(None)
                    )
                )
                instances = result.scalars().all()

                # Populate in-memory sessions dict
                for instance in instances:
                    if instance.character_id and instance.session_id:
                        self.sessions[instance.character_id] = instance.session_id
                        logger.info(f"[SPECIALIST_DB] Loaded session for {instance.character_id}: {instance.session_id}")

                if instances:
                    print(f"[SPECIALIST_DB] Loaded {len(instances)} specialist sessions from database")
                    logger.info(f"[SPECIALIST_DB] Loaded {len(instances)} specialist sessions")

            self._db_loaded = True

        except Exception as e:
            logger.error(f"[SPECIALIST_DB] Failed to load sessions: {e}", exc_info=True)
            self._db_loaded = True  # Mark as loaded to avoid repeated failures

    async def _save_session_to_db(self, agent: str, session_id: str, orchestrator_session_id: str, project_path: str):
        """Save or update specialist session in database."""
        try:
            from ..core.database import AsyncSessionLocal
            from ..models.database import AgentInstance as DBAgentInstance
            from sqlalchemy import select
            from datetime import datetime

            async with AsyncSessionLocal() as db:
                # Create unique instance_id for specialist
                instance_id = f"{orchestrator_session_id}__specialist__{agent}"

                # Check if session already exists
                result = await db.execute(
                    select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
                )
                instance = result.scalar_one_or_none()

                if instance:
                    # Update existing session
                    if not instance.session_id:
                        instance.session_id = session_id
                        await db.commit()
                        logger.info(f"[SPECIALIST_DB] Updated session_id for {agent}: {session_id}")
                        print(f"[SPECIALIST_DB] Updated session_id for {agent}: {session_id}")
                else:
                    # Create new database record
                    new_instance = DBAgentInstance(
                        instance_id=instance_id,
                        character_id=agent,
                        project_path=project_path,
                        role="specialist",
                        status="active",
                        session_id=session_id,
                        parent_tool_use_id=orchestrator_session_id,
                        started_at=datetime.utcnow(),
                    )
                    db.add(new_instance)
                    await db.commit()
                    logger.info(f"[SPECIALIST_DB] Saved session for {agent}: {session_id}")
                    print(f"[SPECIALIST_DB] Saved session to database: {agent} ({instance_id})")

        except Exception as e:
            logger.error(f"[SPECIALIST_DB] Failed to save session for {agent}: {e}", exc_info=True)

    async def call_agent(
        self,
        agent: str,
        message: str,
        updated_context: str,
        project_path: str,
        orchestrator_session_id: str,
    ) -> str:
        """
        Call a specialist agent with streaming support.

        Args:
            agent: Name of the agent (character name)
            message: Message to send to the agent
            updated_context: Updated context from the orchestrator
            project_path: Path to the project
            orchestrator_session_id: Session ID of the orchestrator calling this specialist

        Returns:
            The agent's response text
        """
        from pathlib import Path

        # Load sessions from database if not already loaded
        await self._load_sessions_from_db()

        # The project_path is actually the orchestrator's session directory
        # (e.g., /path/to/project/.sessions/{orchestrator_id})
        # Use it directly as the session_dir for the specialist
        session_dir = Path(project_path)
        print(f"[AGENT] Starting {agent}")
        print(f"[AGENT] Session directory: {session_dir}")
        print(f"[AGENT] Updated context: {updated_context[:100]}..." if updated_context else "[AGENT] No context")
        logger.info(f"[AGENT] Starting {agent}")
        logger.info(f"  Session directory: {session_dir}")
        logger.info(f"  Updated context: {updated_context[:100]}..." if updated_context else "  No context")

        # Notify that agent is starting
        await self.put_message(orchestrator_session_id, {
            "type": "agent_started",
            "agent": agent,
            "message": message,
        })

        try:
            # Load character configuration from filesystem
            from ..core.config import settings
            from ..utils.character_file import CharacterFile
            from pathlib import Path

            # agent parameter is the character ID
            char_id = agent
            char_dir = settings.characters_dir / char_id
            char_file_path = char_dir / "agent.md"

            if not char_file_path.exists():
                raise ValueError(f"Character '{agent}' not found at {char_file_path}")

            # Load character from file
            char_file = CharacterFile.from_file(char_file_path)

            # Get character data
            char_description = char_file.description
            char_personality = char_file.personality
            char_model = char_file.default_model

            # Get capabilities
            allowed_tools = char_file.capabilities.get("allowed_tools", []) if char_file.capabilities else []
            allowed_skills = char_file.capabilities.get("allowed_skills", []) if char_file.capabilities else []
            allowed_mcp_servers = char_file.capabilities.get("allowed_mcp_servers", []) if char_file.capabilities else []
            allowed_custom_tools = char_file.capabilities.get("allowed_custom_tools", []) if char_file.capabilities else []

            print(f"[AGENT] {char_file.name} (ID: {char_id})")
            print(f"[AGENT] Tools: {allowed_tools}")
            print(f"[AGENT] Skills: {allowed_skills}")
            print(f"[AGENT] MCP Servers: {allowed_mcp_servers}")
            print(f"[AGENT] Custom Tools: {allowed_custom_tools}")
            logger.info(f"[AGENT] {char_file.name} (ID: {char_id})")
            logger.info(f"[AGENT] Tools: {allowed_tools}")
            logger.info(f"[AGENT] Skills: {allowed_skills}")
            logger.info(f"[AGENT] MCP Servers: {allowed_mcp_servers}")
            logger.info(f"[AGENT] Custom Tools: {allowed_custom_tools}")

            # Load all .md files in character directory (following symlinks)
            md_files = sorted(char_dir.glob("*.md"))
            agent_prompt_parts = []

            for md_file in md_files:
                logger.info(f"[AGENT] Loading {md_file.name} for {agent}")
                content = md_file.read_text()

                # Extract content after YAML frontmatter (if present)
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    # Has frontmatter, use content after it
                    agent_prompt_parts.append(parts[2].strip())
                else:
                    # No frontmatter, use entire content
                    agent_prompt_parts.append(content.strip())

            if agent_prompt_parts:
                agent_prompt = "\n\n".join(agent_prompt_parts)
                logger.info(f"[AGENT] Loaded {len(md_files)} config files for {agent}")
            else:
                logger.warning(f"[AGENT] No .md files found in {char_dir}")
                agent_prompt = char_personality or ""

            # Symlink agent config and skills into session's agents/ directory for easy access
            import os
            from ..utils.context_files import setup_session_directory_structure

            # Ensure session directory structure exists
            setup_session_directory_structure(session_dir)

            # Create symlink in agents/ subdirectory
            agents_dir = session_dir / "agents"
            agent_session_link = agents_dir / char_id

            # Create symlink to agent's character directory if it doesn't exist
            if not agent_session_link.exists():
                try:
                    os.symlink(char_dir, agent_session_link, target_is_directory=True)
                    logger.info(f"[AGENT] Created symlink: {agent_session_link} -> {char_dir}")
                except FileExistsError:
                    pass  # Symlink already exists
                except Exception as e:
                    logger.warning(f"[AGENT] Failed to create symlink for {agent}: {e}")

            # Check if we have a previous session
            resume_session = self.sessions.get(agent)

            # Load and filter MCP servers
            from .mcp_config import get_mcp_servers_for_character
            filtered_mcp_servers = get_mcp_servers_for_character(allowed_mcp_servers)

            print(f"[AGENT] Allowed MCP servers from capabilities: {allowed_mcp_servers}")
            print(f"[AGENT] Filtered MCP servers: {list(filtered_mcp_servers.keys()) if filtered_mcp_servers else 'None'}")
            logger.info(f"[AGENT] Allowed MCP servers from capabilities: {allowed_mcp_servers}")
            logger.info(f"[AGENT] Filtered MCP servers: {list(filtered_mcp_servers.keys()) if filtered_mcp_servers else 'None'}")

            # Resolve custom tools and create MCP servers
            if allowed_custom_tools:
                from ..services.claude_client import resolve_custom_tools
                logger.info(f"[AGENT] Resolving custom tools: {allowed_custom_tools}")
                custom_mcp_servers = await resolve_custom_tools(
                    custom_tool_ids=allowed_custom_tools,
                    character_id=char_id,
                    project_path=str(session_dir)
                )

                # Merge custom tool MCP servers
                if filtered_mcp_servers is None:
                    filtered_mcp_servers = {}
                filtered_mcp_servers.update(custom_mcp_servers)
                logger.info(f"[AGENT] Added {len(custom_mcp_servers)} custom tool MCP servers")

            # Build allowed tools list - combine character tools + MCP server prefixes + custom tools
            # Using server-level prefixes (mcp__servername) grants access to ALL tools from that server
            mcp_tool_prefixes = [f"mcp__{server}" for server in allowed_mcp_servers]
            all_allowed_tools = allowed_tools.copy() if allowed_tools else []
            all_allowed_tools.extend(mcp_tool_prefixes)

            # Add custom tools with MCP prefix
            if allowed_custom_tools:
                for tool_id in allowed_custom_tools:
                    mcp_tool_name = f"mcp__custom_tools__{tool_id}"
                    all_allowed_tools.append(mcp_tool_name)
                logger.info(f"[AGENT] Custom tools available: {allowed_custom_tools}")

            print(f"[AGENT] Final allowed tools: {all_allowed_tools}")

            # Create agent options (following test_47 pattern)
            # Use setting_sources to load skills, but DON'T use agents parameter
            # Instead, embed agent instructions in the query
            if resume_session:
                logger.info(f"[AGENT] Resuming session for {agent}: {resume_session}")
                agent_options = ClaudeAgentOptions(
                    cwd=str(session_dir),  # Work in session directory for context isolation
                    resume=resume_session,
                    include_partial_messages=True,
                    setting_sources=["project"],  # Load skills from .claude/
                    mcp_servers=filtered_mcp_servers or None,
                    allowed_tools=all_allowed_tools if all_allowed_tools else None,
                )
            else:
                logger.info(f"[AGENT] Creating new session for {agent}")
                agent_options = ClaudeAgentOptions(
                    cwd=str(session_dir),  # Work in session directory for context isolation
                    include_partial_messages=True,
                    setting_sources=["project"],  # Load skills from .claude/
                    mcp_servers=filtered_mcp_servers or None,
                    allowed_tools=all_allowed_tools if all_allowed_tools else None,
                )

            response_text = ""
            new_session_id = None

            # Build contextual instructions for specialist
            context_instructions = f"""
## Session Directory Structure

Your working directory: `{session_dir}`

**Your Configuration**: See `agents/{char_id}/agent.md` for your capabilities and skills

**Directory Organization**:
- `agents/` - Agent configurations (your config is at `agents/{char_id}/`)
- `working/` - Create working files here during execution
- `result/` - Place final deliverables here
- `SESSION.md` - Session context and requirements (READ THIS FIRST)

**Workflow**:
1. Read `SESSION.md` to understand the task
2. Use `working/` for intermediate work
3. Put final outputs in `result/`

**Accessing Context**:
- Other sessions: `cd ../ && ls` then read `../<session-id>/SESSION.md`
- Project root: `cd ../../` (two levels up)
- Project context: `cat ../../PROJECT.md` (if exists)

## Markdown Formatting Guidelines

Always use proper Markdown syntax in your responses for better readability:

**Code and Commands**:
- Inline code: Use backticks for `code`, `commands`, `file.txt`, `variables`
- Code blocks: Use triple backticks with language for multi-line code
  ```python
  def example():
      return "formatted code"
  ```

**Structure**:
- Use `#` for headings (# Main, ## Section, ### Subsection)
- Use `-` or `*` for bullet lists
- Use `1.` for numbered lists
- Use `>` for blockquotes
- Use `**bold**` for emphasis, `*italic*` for secondary emphasis

**Links and References**:
- File references: `path/to/file.txt`
- Links: `[description](url)`
- Horizontal rule: `---`

**Tables** (when needed):
```
| Column 1 | Column 2 |
|----------|----------|
| Data     | Data     |
```

Always format your responses with proper Markdown to ensure they render beautifully in the UI.
"""

            async with ClaudeSDKClient(options=agent_options) as agent_client:
                # Build query - embed agent instructions on first call (test_47 pattern)
                # Message is always in first person (user talking to agent)
                # Context provides team info and dependencies
                if resume_session:
                    # Resuming - provide updated context (if any) and the message
                    if updated_context:
                        full_query = f"[Updated context: {updated_context}]\n\n{message}"
                    else:
                        full_query = message
                else:
                    # First time - embed agent instructions, context, and directory guidance
                    context_section = f"[Context: {updated_context}]" if updated_context else ""
                    full_query = f"{agent_prompt}\n\n{context_instructions}\n\n{context_section}\n\n{message}"

                # Query the character agent (SDK automatically uses the defined agent)
                await agent_client.query(full_query)

                # Stream responses
                async for msg in agent_client.receive_messages():
                    # Capture session ID
                    if isinstance(msg, SystemMessage) and msg.subtype == "init":
                        new_session_id = msg.data.get("session_id")
                        logger.info(f"[AGENT] Session ID: {new_session_id}")

                    # Stream text deltas
                    elif isinstance(msg, StreamEvent):
                        event_type = msg.event.get("type", "")
                        if event_type == "content_block_delta":
                            delta = msg.event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                response_text += text
                                await self.put_message(orchestrator_session_id, {
                                    "type": "agent_delta",
                                    "agent": agent,
                                    "text": text,
                                })

                    # Complete message (for non-streaming parts)
                    elif isinstance(msg, AssistantMessage):
                        from claude_agent_sdk import ToolUseBlock, ToolResultBlock
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                # Only add if not already from streaming
                                if block.text not in response_text:
                                    response_text += block.text
                                    print(f"[AGENT] Emitting agent_text from {agent}: {block.text[:100]}...")
                                    logger.info(f"[AGENT] Emitting agent_text from {agent}: {len(block.text)} chars")
                                    await self.put_message(orchestrator_session_id, {
                                        "type": "agent_text",
                                        "agent": agent,
                                        "text": block.text,
                                    })
                            elif isinstance(block, ToolUseBlock):
                                # Specialist agent is using a tool
                                import json
                                print(f"[AGENT] {agent} used tool: {block.name}")
                                print(f"[AGENT] Tool input: {json.dumps(block.input, indent=2)}")
                                logger.info(f"[AGENT] {agent} used tool: {block.name}")
                                logger.info(f"[AGENT] Tool input: {json.dumps(block.input)}")

                                # Don't inject tool marker - tool calls will be separate messages

                                await self.put_message(orchestrator_session_id, {
                                    "type": "agent_tool_use",
                                    "agent": agent,
                                    "tool_name": block.name,
                                    "tool_args": block.input,
                                })
                            elif isinstance(block, ToolResultBlock):
                                # Tool execution result
                                import json
                                result_str = str(block.content) if block.content else "None"
                                # Truncate very long results for logging
                                result_preview = result_str[:500] + "..." if len(result_str) > 500 else result_str
                                print(f"[AGENT] Tool result: {result_preview}")
                                logger.info(f"[AGENT] Tool result (length: {len(result_str)} chars)")
                                logger.debug(f"[AGENT] Full tool result: {result_str}")

                    # Check for completion
                    elif hasattr(msg, "total_cost_usd"):
                        from datetime import datetime
                        timestamp = datetime.utcnow().isoformat()
                        logger.info(f"[AGENT] {agent} completed (${msg.total_cost_usd:.4f}) at {timestamp}")
                        print(f"[AGENT] {agent} completed at {timestamp}")

                        # Send the complete response for persistence
                        # This ensures the full message is saved even if it was streamed via deltas
                        if response_text:
                            print(f"[AGENT] Sending final response from {agent}: {len(response_text)} chars at {timestamp}")
                            logger.info(f"[AGENT] Sending final response from {agent} for persistence")
                            await self.put_message(orchestrator_session_id, {
                                "type": "agent_response_complete",
                                "agent": agent,
                                "text": response_text,
                                "timestamp": timestamp,
                            })

                        await self.put_message(orchestrator_session_id, {
                            "type": "agent_completed",
                            "agent": agent,
                            "cost": msg.total_cost_usd,
                            "timestamp": timestamp,
                        })
                        print(f"[AGENT] Events queued for {agent} at {timestamp}")
                        break

            # Save session ID for resumption
            if new_session_id:
                self.sessions[agent] = new_session_id
                # Persist to database
                await self._save_session_to_db(
                    agent=agent,
                    session_id=new_session_id,
                    orchestrator_session_id=orchestrator_session_id,
                    project_path=project_path
                )

            return response_text

        except Exception as e:
            logger.error(f"[AGENT] Error in {agent}: {e}", exc_info=True)
            await self.put_message(orchestrator_session_id, {
                "type": "agent_error",
                "agent": agent,
                "error": str(e),
            })
            return f"Error: {str(e)}"


# Global session manager
session_manager = AgentSessionManager()


def create_call_agent_tool(project_path: str, available_agents: list[str], orchestrator_session_id: str):
    """
    Create the call_agent MCP tool.

    Args:
        project_path: Path to the project (for .claude/agents/)
        available_agents: List of available agent names
        orchestrator_session_id: The orchestrator's session ID for queue routing

    Returns:
        Decorated tool function
    """

    async def call_agent_impl(args: dict[str, Any]) -> dict[str, Any]:
        """
        Call a specialist agent for help.

        Args (from dict):
            agent: Name of the agent to consult
            message: Message to send (in first person, as if user talking directly)
            updated_context: Team context and workflow information
        """
        agent = args.get("agent", "")
        message = args.get("message", "")
        updated_context = args.get("updated_context", "")

        if not agent or not message:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: agent and message are required"
                }]
            }

        if agent not in available_agents:
            available = ", ".join(available_agents)
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Unknown agent '{agent}'. Available: {available}"
                }]
            }

        # Run the agent (this blocks until complete, but streams to queue)
        response = await session_manager.call_agent(
            agent=agent,
            message=message,
            updated_context=updated_context,
            project_path=project_path,
            orchestrator_session_id=orchestrator_session_id,
        )

        # Return result to parent agent
        return {
            "content": [{
                "type": "text",
                "text": f"[{agent}] {response}"
            }]
        }

    return call_agent_impl


def create_agent_mcp_server(project_path: str, available_agents: list[str], orchestrator_session_id: str):
    """
    Create MCP server with call_agent tool.

    Args:
        project_path: Path to project
        available_agents: List of agent names from .claude/agents/
        orchestrator_session_id: The orchestrator's session ID for queue routing

    Returns:
        MCP server instance
    """
    call_func = create_call_agent_tool(project_path, available_agents, orchestrator_session_id)

    # Decorate with @tool using Test 47 pattern
    agents_list = ", ".join(available_agents)
    decorated_tool = tool(
        "call_agent",
        f"Call a specialist agent for help. Available agents: {agents_list}",
        {
            "agent": str,
            "message": str,
            "updated_context": str,
        }
    )(call_func)

    return create_sdk_mcp_server(
        name="agents",
        version="1.0.0",
        tools=[decorated_tool]
    )


def get_available_agents(project_path: str) -> list[str]:
    """
    Scan .claude/agents/ directory for available agents.

    Args:
        project_path: Path to project

    Returns:
        List of agent names (subdirectory names)
    """
    agents_dir = Path(project_path) / ".claude" / "agents"
    if not agents_dir.exists():
        return []

    agents = []
    for item in agents_dir.iterdir():
        if item.is_dir() and (item / "agent.md").exists():
            agents.append(item.name)

    return agents
