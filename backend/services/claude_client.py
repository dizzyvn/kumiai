"""Claude SDK client wrapper and custom MCP tools."""
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,
    tool,
    create_sdk_mcp_server,
)
from typing import Any, Optional
import asyncio
import logging

# Import PM tools
from ..tools.pm_tools import contact_pm, remind, show_file, contact_session_specialist, PM_MANAGEMENT_TOOLS

# Import skill-assistant tools
from ..tools.skill_assistant_tools import SKILL_ASSISTANT_TOOLS

# Import character-assistant tools
from ..tools.character_assistant_tools import CHARACTER_ASSISTANT_TOOLS

# Import tool provider system
from ..tools.provider_manager import ToolProviderManager
from ..tools.providers import MCPProvider, PythonProvider, HTTPProvider
from ..tools.provider_base import ToolContext, ProviderType

logger = logging.getLogger(__name__)


# ============================================================================
# SDK Hooks - Context Injection
# ============================================================================

async def inject_session_id_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
    """
    Auto-inject session_id into cross-session messaging tools.

    This hook intercepts remind, contact_pm, contact_session, and notify_user tool calls
    and automatically injects the current Claude SDK session_id. The session_id parameter
    is not exposed in the tool schema, so agents cannot provide it - it's always
    injected by this hook.

    Args:
        input_data: Hook input data containing tool_name, tool_input, session_id, etc.
        tool_use_id: Tool use identifier
        context: Hook context (unused in Python SDK)

    Returns:
        Hook response with updatedInput containing injected session_id
    """
    logger.info(f"[HOOK] Called with event: {input_data.get('hook_event_name')}, tool: {input_data.get('tool_name')}")

    # Only process PreToolUse events
    if input_data.get('hook_event_name') != 'PreToolUse':
        return {}

    # Check if this is a cross-session messaging tool
    tool_name = input_data.get('tool_name', '')
    messaging_tools = [
        'mcp__common_tools__remind',
        'mcp__common_tools__contact_pm',
        'mcp__pm_management__contact_session',
        'mcp__pm_management__notify_user'
    ]

    if tool_name not in messaging_tools:
        logger.debug(f"[HOOK] Skipping tool (not a messaging tool): {tool_name}")
        return {}

    tool_input = input_data.get('tool_input', {})

    # Get session_id from hook context (provided by Claude SDK)
    session_id = input_data.get('session_id')
    if not session_id:
        logger.error("[HOOK] ✗ No session_id in hook input, cannot inject!")
        logger.error(f"[HOOK] Available keys: {list(input_data.keys())}")
        return {}

    logger.info(f"[HOOK] ✓ Auto-injecting session_id: {session_id} into {tool_name}")

    # Inject session_id into tool input (always inject since it's not in the schema)
    return {
        'hookSpecificOutput': {
            'hookEventName': input_data['hook_event_name'],
            'permissionDecision': 'allow',
            'updatedInput': {
                **tool_input,
                'session_id': session_id  # Auto-injected, invisible to agent
            }
        }
    }


async def normalize_file_path_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
    """
    Normalize file paths in show_file tool calls.

    This hook intercepts show_file tool calls and converts relative paths
    to absolute paths, while also validating against path traversal attacks.

    Args:
        input_data: Hook input data containing tool_name, tool_input, etc.
        tool_use_id: Tool use identifier
        context: Hook context (unused in Python SDK)

    Returns:
        Hook response with normalized file path
    """
    from pathlib import Path
    import os

    logger.info(f"[HOOK] normalize_file_path called with event: {input_data.get('hook_event_name')}, tool: {input_data.get('tool_name')}")

    # Only process PreToolUse events
    if input_data.get('hook_event_name') != 'PreToolUse':
        return {}

    # Check if this is show_file tool
    tool_name = input_data.get('tool_name', '')
    if not tool_name.endswith('show_file'):
        logger.debug(f"[HOOK] Skipping tool (not show_file): {tool_name}")
        return {}

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('path', '')

    if not file_path:
        logger.warning("[HOOK] No path provided in show_file call")
        return {}

    # Security: Block path traversal attempts
    if '..' in file_path:
        logger.warning(f"[HOOK] ✗ Blocked path traversal attempt: {file_path}")
        return {
            'hookSpecificOutput': {
                'hookEventName': input_data['hook_event_name'],
                'permissionDecision': 'deny',
                'error': 'Path traversal (..) is not allowed for security reasons'
            }
        }

    # Normalize path to absolute
    try:
        path_obj = Path(file_path)

        # If already absolute, use as-is
        if path_obj.is_absolute():
            normalized_path = str(path_obj.resolve())
        else:
            # Relative path - expand from current working directory
            normalized_path = str(path_obj.expanduser().resolve())

        logger.info(f"[HOOK] ✓ Normalized path: {file_path} → {normalized_path}")

        return {
            'hookSpecificOutput': {
                'hookEventName': input_data['hook_event_name'],
                'permissionDecision': 'allow',
                'updatedInput': {
                    **tool_input,
                    'path': normalized_path
                }
            }
        }

    except Exception as e:
        logger.error(f"[HOOK] ✗ Error normalizing path {file_path}: {e}")
        return {
            'hookSpecificOutput': {
                'hookEventName': input_data['hook_event_name'],
                'permissionDecision': 'deny',
                'error': f'Invalid file path: {str(e)}'
            }
        }


# ============================================================================
# Custom MCP Tools
# ============================================================================

# Common tools MCP server - universal tools available to ALL session types
common_tools = create_sdk_mcp_server(
    name="common_tools",
    version="1.0.0",
    tools=[contact_pm, remind, show_file, contact_session_specialist]  # Inter-agent communication + self-management + file display
)

# Backward compatibility alias
kumiAI_tools = common_tools

pm_management_tools = create_sdk_mcp_server(
    name="pm_management",
    version="1.0.0",
    tools=PM_MANAGEMENT_TOOLS  # spawn_instance, get_project_status, etc.
)

# Create skill-assistant tools MCP server
skill_assistant_tools = create_sdk_mcp_server(
    name="skill_assistant",
    version="1.0.0",
    tools=SKILL_ASSISTANT_TOOLS  # search_custom_tools, search_skills, etc.
)

# Create character-assistant tools MCP server
character_assistant_tools = create_sdk_mcp_server(
    name="character_assistant",
    version="1.0.0",
    tools=CHARACTER_ASSISTANT_TOOLS  # set_agent_tools, set_agent_mcp_servers, etc.
)


# ============================================================================
# Tool Provider System
# ============================================================================

# Global provider manager instance
_provider_manager: Optional[ToolProviderManager] = None
_provider_init_lock = asyncio.Lock()


async def get_provider_manager() -> ToolProviderManager:
    """
    Get or create the global ToolProviderManager instance.

    Returns:
        Initialized ToolProviderManager
    """
    global _provider_manager

    if _provider_manager is not None:
        return _provider_manager

    async with _provider_init_lock:
        # Double-check after acquiring lock
        if _provider_manager is not None:
            return _provider_manager

        logger.info("Initializing global ToolProviderManager...")

        # Create manager
        manager = ToolProviderManager()

        # Register MCP Provider (for backward compatibility)
        mcp_provider = MCPProvider()
        manager.register_provider(mcp_provider)

        # Register Python Provider
        python_provider = PythonProvider()
        manager.register_provider(python_provider)

        # Register HTTP Provider
        http_provider = HTTPProvider()
        manager.register_provider(http_provider)

        # Initialize all providers
        await manager.initialize({
            "mcp": {},  # MCP config loaded from ~/.claude.json
            "python": {},  # No config needed for Python
            "http": {
                "timeout": 30,
                "endpoints": {}  # Can be configured later
            }
        })

        # Register custom Python tools
        from ..tools.custom_tools import register_custom_tools
        register_custom_tools(python_provider)
        logger.info("Custom tools registered")

        _provider_manager = manager
        logger.info("ToolProviderManager initialized successfully")

        return _provider_manager


async def resolve_custom_tools(
    custom_tool_ids: list[str],
    character_id: Optional[str] = None,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    project_id: Optional[str] = None
) -> dict:
    """
    Resolve custom tools from provider system and convert to MCP servers for Claude SDK.

    For custom tools (python__, http__), we need to create wrapper MCP servers
    because Claude SDK only accepts MCP format. The provider system handles
    the actual execution.

    Args:
        custom_tool_ids: List of custom tool IDs (e.g., ["python__math__calc", "http__slack__notify"])
        character_id: Character ID for context
        project_path: Project path for context
        session_id: Session ID for context
        project_id: Project ID for context

    Returns:
        Dict mapping MCP server names to server objects

    Note:
        Custom tools will be prefixed with their provider type when passed to Claude SDK.
        Example: python__math__calc becomes available as "python__math__calc" tool.
    """
    if not custom_tool_ids:
        logger.debug("No custom tools requested")
        return {}

    logger.info(f"[CUSTOM_TOOLS] Resolving {len(custom_tool_ids)} custom tools")
    logger.debug(f"[CUSTOM_TOOLS] Tool IDs: {custom_tool_ids}")

    manager = await get_provider_manager()

    # Create tool context with all available information
    context = ToolContext(
        character_id=character_id,
        session_id=session_id,
        project_id=project_id,
        working_directory=project_path
    )

    # Get tool definitions from provider manager
    tool_defs = await manager.get_tools_by_ids(custom_tool_ids, context)

    if not tool_defs:
        logger.warning(f"[CUSTOM_TOOLS] No custom tools found for IDs: {custom_tool_ids}")
        return {}

    logger.info(f"[CUSTOM_TOOLS] Resolved {len(tool_defs)} custom tools: {[t.tool_id for t in tool_defs]}")

    # Log each tool being prepared
    for tool_def in tool_defs:
        logger.debug(f"[CUSTOM_TOOLS] Preparing tool: {tool_def.tool_id}")
        logger.debug(f"  - Provider: {tool_def.provider}")
        logger.debug(f"  - Category: {tool_def.category}")
        logger.debug(f"  - Name: {tool_def.name}")
        logger.debug(f"  - Description: {tool_def.description}")

    # Create wrapper functions for all tools
    tool_wrappers = []
    for tool_def in tool_defs:
        # Create wrapper function that delegates to provider manager
        # Use closure with default argument to capture tool_def correctly
        def create_tool_wrapper(td):
            """Create a wrapper function for a specific tool."""
            async def tool_wrapper(args: dict[str, Any]) -> dict[str, Any]:
                """Execute tool via provider manager."""
                try:
                    # Log tool execution attempt
                    logger.info(f"[CUSTOM_TOOLS] Executing tool: {td.tool_id}")

                    # Execute via provider manager
                    result = await manager.execute_tool(
                        tool_id=td.tool_id,
                        arguments=args,
                        context=context
                    )

                    logger.info(f"[CUSTOM_TOOLS] Tool execution completed: success={result.success}")

                    # Convert ToolResult to Claude SDK format
                    if result.success:
                        # Format result as text content
                        # If result is a dict/list, format as JSON for better readability
                        import json
                        if isinstance(result.result, (dict, list)):
                            result_text = json.dumps(result.result, indent=2, ensure_ascii=False)
                        elif result.result is not None:
                            result_text = str(result.result)
                        else:
                            result_text = "Success"

                        logger.info(f"Custom tool {td.tool_id} executed successfully")
                        logger.debug(f"Tool result: {result_text[:200]}...")

                        return {
                            "content": [{
                                "type": "text",
                                "text": result_text
                            }]
                        }
                    else:
                        # Return error message
                        logger.error(f"[CUSTOM_TOOLS] Tool {td.tool_id} failed: {result.error}")
                        return {
                            "content": [{
                                "type": "text",
                                "text": f"Error: {result.error}"
                            }]
                        }
                except Exception as e:
                    logger.error(f"[CUSTOM_TOOLS] Exception executing tool {td.tool_id}: {e}", exc_info=True)
                    import traceback
                    error_details = traceback.format_exc()
                    logger.error(f"[CUSTOM_TOOLS] Full traceback:\n{error_details}")
                    return {
                        "content": [{
                            "type": "text",
                            "text": f"Tool execution failed: {str(e)}\n\nDetails: {error_details[:500]}"
                        }]
                    }

            return tool_wrapper

        # Create wrapper
        wrapper = create_tool_wrapper(tool_def)

        # Convert input_schema to simple type dict for @tool decorator
        # The input_schema from provider is JSON Schema, need to extract types
        param_schema = {}
        if "properties" in tool_def.input_schema:
            for param_name, param_def in tool_def.input_schema["properties"].items():
                # Map JSON Schema types to Python types
                json_type = param_def.get("type", "string")
                param_schema[param_name] = {
                    "string": str,
                    "number": float,
                    "integer": int,
                    "boolean": bool,
                    "array": list,
                    "object": dict,
                }.get(json_type, str)

        # Apply @tool decorator
        # Use the original tool_id as the tool name in the MCP server
        logger.debug(f"[CUSTOM_TOOLS] Decorating tool {tool_def.tool_id} with params: {param_schema}")
        decorated_tool = tool(
            tool_def.tool_id,
            tool_def.description,
            param_schema
        )(wrapper)

        tool_wrappers.append(decorated_tool)
        logger.debug(f"[CUSTOM_TOOLS] Tool {tool_def.tool_id} wrapped and decorated successfully")

    # Create a single MCP server for all custom tools
    mcp_server = create_sdk_mcp_server(
        name="custom_tools",
        version="1.0.0",
        tools=tool_wrappers
    )

    logger.info(f"Created 'custom_tools' MCP server with {len(tool_wrappers)} tools")

    return {"custom_tools": mcp_server}


# ============================================================================
# Claude Client Manager
# ============================================================================

class ClaudeClientManager:
    """Manages Claude SDK client instances for agents."""

    def __init__(self):
        self.clients: dict[str, ClaudeSDKClient] = {}
        self.sessions: dict[str, str] = {}  # instance_id -> session_id
        self._lock = asyncio.Lock()

    async def create_client(
        self,
        instance_id: str,
        character_name: str,
        character_description: str,
        character_personality: Optional[str],
        allowed_tools: list[str],
        project_path: str,
        allowed_custom_tools: Optional[list[str]] = None,
        model: str = "sonnet",
        selected_specialists: Optional[list[str]] = None,
        resume_session: Optional[str] = None,
        system_prompt_append: Optional[str] = None,
        role: str = "orchestrator",  # orchestrator, pm, specialist
    ) -> ClaudeSDKClient:
        """Create a new Claude SDK client for an agent."""
        from ..utils.multi_agent_streaming import (
            create_agent_mcp_server,
            get_available_agents,
        )

        async with self._lock:
            logger.info(f"[CLIENT] Creating client with role: {role}")

            # Build MCP servers
            # For plain Claude mode (no character), don't include kumiAI - only specialists
            if character_name:
                mcp_servers = {"kumiAI": kumiAI_tools}
            else:
                mcp_servers = {}

            # Build allowed_tools list from character capabilities and role
            # Start with character's allowed_tools, or empty list if none
            final_allowed_tools = allowed_tools.copy() if allowed_tools else []

            # Resolve custom tools and create MCP servers
            if allowed_custom_tools:
                logger.info(f"[CLIENT] Resolving custom tools: {allowed_custom_tools}")
                custom_mcp_servers = await resolve_custom_tools(
                    custom_tool_ids=allowed_custom_tools,
                    character_id=character_name,  # Use character name as ID
                    project_path=project_path,
                    session_id=instance_id,
                    project_id=None  # Will be set later if available
                )

                # Merge custom tool MCP servers into mcp_servers dict
                mcp_servers.update(custom_mcp_servers)

                # Add MCP-prefixed tool names to allowed_tools
                # Custom tools are exposed as mcp__custom_tools__<tool_id>
                added_tool_names = []
                for tool_id in allowed_custom_tools:
                    mcp_tool_name = f"mcp__custom_tools__{tool_id}"
                    final_allowed_tools.append(mcp_tool_name)
                    added_tool_names.append(mcp_tool_name)

                logger.info(f"[CLIENT] Added {len(custom_mcp_servers)} custom tool MCP servers")
                logger.info(f"[CLIENT] Custom tools available: {allowed_custom_tools}")
                logger.info(f"[CLIENT] MCP tool names added to allowed_tools: {added_tool_names}")

            # Add PM tools based on role (Phase 2.4 - Tool Access Control)
            logger.info(f"[CLIENT] Checking role for tool assignment: role='{role}', type={type(role)}")
            if role == "orchestrator":
                # Orchestrators can contact PM via kumiAI server
                final_allowed_tools.append("mcp__kumiAI")
                logger.info(f"[CLIENT] Enabled kumiAI tools for orchestrator (includes contact_pm)")
            elif role == "pm":
                # PM gets full project management capabilities
                mcp_servers["pm_management"] = pm_management_tools
                # Enable all PM management MCP tools
                final_allowed_tools.append("mcp__pm_management")
                logger.info(f"[CLIENT] Added PM management tools for PM agent")
            # Specialists get no PM tools (base tools only)

            # Use selected specialists if provided, otherwise scan all
            if selected_specialists:
                # Filter to only selected team members
                # Specialists are identified by their character ID
                # Character data comes from filesystem, not database
                available_specialists = selected_specialists.copy()

                if available_specialists:
                    logger.info(f"[CLIENT] Selected specialists: {available_specialists}")
                    # Create agent MCP server (with orchestrator session ID for queue routing)
                    agent_server = create_agent_mcp_server(
                        project_path=project_path,
                        available_agents=available_specialists,
                        orchestrator_session_id=instance_id,  # Use instance_id as orchestrator session ID
                    )
                    mcp_servers["agents"] = agent_server

                    # Add call_agent tool for orchestrator coordination
                    final_allowed_tools.append("mcp__agents__call_agent")
                    logger.info(f"[CLIENT] Added call_agent tool for orchestrator")
                    logger.info(f"[CLIENT] Available agents: {', '.join(available_specialists)}")
                else:
                    logger.error(f"[CLIENT] No specialists found. Requested IDs: {selected_specialists}. Database may not be seeded.")
                    raise ValueError(f"No specialists found for IDs: {selected_specialists}")

            # Configure options with optional resume
            # For plain Claude (no character), follow Test 47 pattern exactly
            # Convert final_allowed_tools to None if empty for Claude SDK compatibility
            tools_for_claude = final_allowed_tools if final_allowed_tools else None

            if character_name:
                # Character mode - load from project
                options_dict = {
                    "cwd": project_path,
                    "setting_sources": ["project"],
                    "allowed_tools": tools_for_claude,
                    "include_partial_messages": True,
                    "mcp_servers": mcp_servers,
                }
            else:
                # Plain Claude mode - Test 47 pattern with cwd for project context
                options_dict = {
                    "cwd": project_path,
                    "mcp_servers": mcp_servers,
                    "allowed_tools": tools_for_claude,
                    "include_partial_messages": True,
                    "permission_mode": "bypassPermissions",  # Skip permission prompts for skill editing
                }
                logger.info(f"[CLIENT] Creating plain Claude with cwd={project_path}, allowed_tools: {tools_for_claude}")

            # Only define agent if character_name provided (Test 47 pattern)
            if character_name:
                agent_def = AgentDefinition(
                    description=character_description,
                    prompt=character_personality or f"You are {character_name}.",
                    tools=tools_for_claude,
                    model=model,
                )
                options_dict["agents"] = {character_name: agent_def}

            # Add resume parameter if session ID provided
            if resume_session:
                logger.info(f"[CLIENT] Creating client with resume: {resume_session}")
                options_dict["resume"] = resume_session

            # Add system prompt with append if provided
            if system_prompt_append:
                logger.info(f"[CLIENT] Adding system prompt append: {system_prompt_append[:100]}...")
                options_dict["system_prompt"] = {
                    "type": "preset",
                    "preset": "claude_code",
                    "append": system_prompt_append
                }

            options = ClaudeAgentOptions(**options_dict)

            # Create client
            client = ClaudeSDKClient(options=options)
            self.clients[instance_id] = client

            return client

    async def get_client(self, instance_id: str) -> Optional[ClaudeSDKClient]:
        """Get existing client for an agent."""
        return self.clients.get(instance_id)

    async def get_or_create_client(self, instance_id: str) -> Optional[ClaudeSDKClient]:
        """
        Get existing client or rebuild from database if not found.

        This method handles session resumption after backend restarts by:
        1. Checking if client exists in memory
        2. If not, loading session metadata from database
        3. Rebuilding the client with all original parameters
        4. Resuming the Claude SDK session if session_id exists

        Args:
            instance_id: The instance/session ID

        Returns:
            ClaudeSDKClient instance or None if session not found in database
        """
        # Check if client already exists in memory
        existing_client = self.clients.get(instance_id)
        if existing_client:
            logger.debug(f"[RESUME] Client already exists for {instance_id}")
            return existing_client

        # Client not in memory - rebuild from database
        logger.info(f"[RESUME] Client not found in memory for {instance_id}, rebuilding from database")

        # Import here to avoid circular dependency
        from ..core.database import AsyncSessionLocal
        from ..models.database import AgentInstance as DBAgentInstance, Project
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            # Load session from database
            result = await db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            instance = result.scalar_one_or_none()

            if not instance:
                logger.warning(f"[RESUME] Session {instance_id} not found in database")
                return None

            logger.info(f"[RESUME] Found session in database: role={instance.role}, project_id={instance.project_id}")

            # Get character info if character_id is set (PM with character)
            character_name = None
            character_description = ""
            character_personality = None
            allowed_tools = []
            allowed_custom_tools = []
            model = "sonnet"

            if instance.character_id:
                # Load character from database
                from ..services.character_service import CharacterService
                character_service = CharacterService(db)
                try:
                    character = await character_service.get_character(instance.character_id)
                    if character:
                        character_name = character.name
                        character_description = character.description or ""
                        character_personality = character.personality
                        allowed_tools = character.capabilities.allowed_tools if character.capabilities else []
                        allowed_custom_tools = character.capabilities.allowed_custom_tools if character.capabilities else []
                        model = character.default_model or "sonnet"
                        logger.info(f"[RESUME] Loaded character: {character_name}")
                except Exception as e:
                    logger.warning(f"[RESUME] Failed to load character {instance.character_id}: {e}")

            # Build system prompt based on role
            system_prompt_append = None

            if instance.role == "pm":
                # Load project for PM role
                project_name = "Unknown Project"
                project_description = ""
                team_member_ids = []

                if instance.project_id:
                    result_proj = await db.execute(
                        select(Project).where(Project.id == instance.project_id)
                    )
                    project = result_proj.scalar_one_or_none()
                    if project:
                        project_name = project.name
                        project_description = project.description or ""
                        team_member_ids = project.team_member_ids or []

                        # NOTE: PROJECT.md regeneration disabled to preserve custom edits
                        # PROJECT.md is only generated once during initial project creation
                        # If you need to regenerate it, manually delete PROJECT.md and recreate the project
                        # logger.info(f"[RESUME] Regenerating PROJECT.md for PM session")
                        # from ..utils.context_files import generate_project_md
                        # try:
                        #     await generate_project_md(
                        #         project_path=instance.project_path,
                        #         project_id=instance.project_id,
                        #         project_name=project.name,
                        #         project_description=project.description,
                        #         team_member_ids=project.team_member_ids,
                        #         pm_character_id=project.pm_id,
                        #     )
                        #     logger.info(f"[RESUME] PROJECT.md regenerated successfully")
                        # except Exception as e:
                        #     logger.warning(f"[RESUME] Failed to regenerate PROJECT.md: {e}")

                # Build PM system prompt
                pm_instructions = f"""

You are the Project Manager - BE CONCISE, minimize explanations.
Project ID: {instance.project_id}
Project Path: {instance.project_path}

IMPORTANT: Read PROJECT.md in your working directory for full project context.

WORKFLOW FOR DEPENDENT TASKS:
1. Spawn session for Task A → update_instance_stage to "active"
2. WAIT for orchestrator completion notification
4. Spawn session for Task B with context from Task A:
   - Include folder paths where Task A outputs are located
   - Reference specific files or results from Task A
   - Provide any relevant context for continuity
5. Repeat: WAIT → Review → Pass Context → Next Task

TOOLS:
- get_project_status(project_id="{instance.project_id}") - Check all instances
- list_team_members(project_id="{instance.project_id}") - See available specialists
- spawn_instance(project_id="{instance.project_id}", session_description="...", project_path="{instance.project_path}", specialists=["id1", "id2"], kanban_stage="backlog|active")
- update_instance_stage(project_id="{instance.project_id}", instance_id="...", new_stage="active|done")
- send_to_instance(project_id="{instance.project_id}", instance_id="...", message="...")

COMMUNICATION STYLE:
- Be BRIEF and action-focused
- Just execute and report outcomes
- Let orchestrators/specialists do the talking to users"""

                system_prompt_append = pm_instructions

            elif instance.role == "orchestrator":
                # Build orchestrator system prompt
                from pathlib import Path
                session_path = str(Path(instance.project_path) / ".sessions" / instance_id)

                orchestrator_instructions = f"""

## Session Directory Structure

Your working directory: `{session_path}`

**Directory Organization**:
- `agents/` - Agent configurations (symlinked when specialists are called)
- `working/` - Create working files here during execution
- `result/` - Place final deliverables here
- `SESSION.md` - Your session context and requirements

**Best Practices**:
1. Use `working/` for intermediate files, notes, and drafts
2. Use `result/` for final outputs that should be delivered

**Accessing Project Context**:
- Project root: `cd ../../` (two levels up)
- Other sessions: `cd ../ && ls` to see other session directories
- Project overview: `cat ../../PROJECT.md` (if exists)

## Message Delegation Protocol

When you receive a message from the user, it is **intended for the team/specialists**, not for you directly as the orchestrator. Your role is to:

1. **Translate to first-person perspective**: Forward the user's request to specialists as if the user is speaking directly to them
2. **Never say "the user wants..."**: Instead, frame it as a direct request (e.g., "Please implement X" instead of "The user wants you to implement X")
3. **Be transparent**: You are a coordinator, not an intermediary shield. Let specialists engage with the request naturally

**Example - DO THIS**:
User says: "Can you add a login form with email validation?"
You call specialist with: "Please add a login form with email validation."

**Example - DON'T DO THIS**:
User says: "Can you add a login form with email validation?"
You call specialist with: "The user wants you to add a login form with email validation."

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
                system_prompt_append = orchestrator_instructions

            # Get specialists list
            selected_specialists = instance.selected_specialists or []

            # Determine project_path based on role
            if instance.role == "orchestrator":
                from pathlib import Path
                project_path = str(Path(instance.project_path) / ".sessions" / instance_id)
            else:
                project_path = instance.project_path

            logger.info(f"[RESUME] Rebuilding client with:")
            logger.info(f"  - role: {instance.role}")
            logger.info(f"  - character_name: {character_name}")
            logger.info(f"  - project_path: {project_path}")
            logger.info(f"  - specialists: {selected_specialists}")
            logger.info(f"  - resume_session: {instance.session_id}")

            # Create the client (will be added to self.clients)
            client = await self.create_client(
                instance_id=instance_id,
                character_name=character_name,
                character_description=character_description,
                character_personality=character_personality,
                allowed_tools=allowed_tools,
                project_path=project_path,
                allowed_custom_tools=allowed_custom_tools,
                model=model,
                selected_specialists=selected_specialists,
                resume_session=instance.session_id,  # Resume previous session if exists
                system_prompt_append=system_prompt_append,
                role=instance.role or "orchestrator",
            )

            # Connect the client
            await client.connect()

            logger.info(f"[RESUME] Client successfully rebuilt and connected for {instance_id}")
            return client

    async def remove_client(self, instance_id: str):
        """Remove and close a client."""
        async with self._lock:
            client = self.clients.pop(instance_id, None)
            if client:
                # Client will be closed when context manager exits
                # or we can manually close if needed
                pass
            self.sessions.pop(instance_id, None)

    def set_session(self, instance_id: str, session_id: str):
        """Store session ID for an agent."""
        self.sessions[instance_id] = session_id

    def get_session(self, instance_id: str) -> Optional[str]:
        """Get session ID for an agent."""
        return self.sessions.get(instance_id)

    def get_instance_id_from_session(self, session_id: str) -> Optional[str]:
        """
        Reverse lookup: Get instance_id from Claude SDK session_id.

        Args:
            session_id: Claude SDK session ID

        Returns:
            instance_id if found, None otherwise
        """
        for instance_id, sid in self.sessions.items():
            if sid == session_id:
                return instance_id
        return None


# Global client manager instance
client_manager = ClaudeClientManager()
