"""PM Agent Management Tools.

These tools enable PM agents to coordinate project workflows, spawn sessions,
and manage orchestrator agents. Access is restricted based on session role.

Design: PM tools accept project_id as an explicit parameter to avoid async
context propagation issues with MCP tool execution.
"""
from claude_agent_sdk import tool
from typing import Any
import logging
import json
from sqlalchemy import select, and_

from ..core.database import AsyncSessionLocal
from ..models.database import AgentInstance as DBAgentInstance
from ..services.sse_manager import sse_manager

logger = logging.getLogger(__name__)


async def get_pm_character_id(project_id: str) -> str | None:
    """Get PM's character ID for sender attribution.

    Args:
        project_id: Project ID to find PM for

    Returns:
        PM character ID (e.g., "shitara") or None if not found
    """
    try:
        async with AsyncSessionLocal() as db:
            pm_result = await db.execute(
                select(DBAgentInstance).where(
                    and_(
                        DBAgentInstance.project_id == project_id,
                        DBAgentInstance.role == "pm"
                    )
                )
            )
            pm_session = pm_result.scalar_one_or_none()

            if pm_session and pm_session.character_id:
                logger.info(f"[PM_TOOLS] Found PM character ID: {pm_session.character_id}")
                return pm_session.character_id
            else:
                logger.warning(f"[PM_TOOLS] No PM session or character_id for project {project_id}")
                return None
    except Exception as e:
        logger.warning(f"[PM_TOOLS] Could not get PM character ID: {e}")
        return None


async def get_pm_context(project_id: str) -> tuple[str, str]:
    """Get PM session for a project.

    Args:
        project_id: The project ID to find PM for

    Returns:
        Tuple of (pm_instance_id, project_id)

    Raises:
        RuntimeError: If no PM exists for the project
    """
    # Query database for PM session in this project
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBAgentInstance).where(
                DBAgentInstance.project_id == project_id,
                DBAgentInstance.role == "pm",
                DBAgentInstance.status != "cancelled"
            )
        )
        pm_instance = result.scalar_one_or_none()
        if not pm_instance:
            raise RuntimeError(f"No PM found for project {project_id}")

        return pm_instance.instance_id, project_id


# ============================================================================
# Shared Cross-Session Messaging Engine
# ============================================================================

async def _resolve_sender_context(session_id: str) -> dict[str, Any]:
    """Resolve sender context from Claude SDK session_id.

    Single optimized query to get all sender information needed for message attribution.

    Args:
        session_id: Claude SDK session ID

    Returns:
        Dict with keys: instance_id, project_id, role, character_id, name

    Raises:
        RuntimeError: If session_id cannot be resolved
    """
    from ..services.claude_client import client_manager
    from ..models.database import Character

    # Step 1: Reverse lookup session_id -> instance_id
    instance_id = client_manager.get_instance_id_from_session(session_id)
    if not instance_id:
        raise RuntimeError(f"Could not resolve session_id {session_id} to instance_id")

    # Step 2: Single query to get instance + character + project info
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBAgentInstance, Character).
            outerjoin(Character, DBAgentInstance.character_id == Character.id).
            where(DBAgentInstance.instance_id == instance_id)
        )
        row = result.one_or_none()

        if not row:
            raise RuntimeError(f"Instance {instance_id} not found in database")

        instance, character = row

        # Build sender context
        # Character.id is the character identifier (e.g., "shitara", "sakura")
        # Use it as the display name if available, otherwise use role
        sender_name = character.id if character else instance.role.upper()

        return {
            "instance_id": instance.instance_id,
            "project_id": instance.project_id,
            "role": instance.role,
            "character_id": instance.character_id,
            "name": sender_name
        }


async def _route_to_pm_from_session(session_id: str) -> str:
    """Route from sender session_id to PM instance_id.

    Optimized query path: session_id -> instance -> project -> pm_instance_id

    Args:
        session_id: Sender's Claude SDK session ID

    Returns:
        PM's instance_id

    Raises:
        RuntimeError: If routing fails at any step
    """
    from ..services.claude_client import client_manager
    from ..models.database import Project

    # Step 1: session_id -> instance_id
    instance_id = client_manager.get_instance_id_from_session(session_id)
    if not instance_id:
        raise RuntimeError(f"Could not resolve session_id {session_id} to instance_id")

    # Step 2: Single query to get instance + project in one go
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBAgentInstance, Project).
            join(Project, DBAgentInstance.project_id == Project.id).
            where(DBAgentInstance.instance_id == instance_id)
        )
        row = result.one_or_none()

        if not row:
            raise RuntimeError(f"Instance {instance_id} or its project not found")

        instance, project = row

        if not project.pm_instance_id:
            raise RuntimeError(f"No PM assigned to project {project.id}")

        logger.info(
            f"[MESSAGING_ENGINE] Routed {instance_id} -> project {project.id} -> PM {project.pm_instance_id}"
        )

        return project.pm_instance_id


async def _validate_pm_routing(
    sender_session_id: str,
    project_id: str,
    target_instance_id: str
) -> None:
    """Validate that sender is PM and target belongs to same project.

    Args:
        sender_session_id: Sender's Claude SDK session ID
        project_id: Expected project ID
        target_instance_id: Target instance ID

    Raises:
        RuntimeError: If validation fails
    """
    from ..services.claude_client import client_manager

    # Resolve sender
    sender_instance_id = client_manager.get_instance_id_from_session(sender_session_id)
    if not sender_instance_id:
        raise RuntimeError(f"Could not resolve sender session_id {sender_session_id}")

    # Single query to validate both sender and target
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBAgentInstance).where(
                DBAgentInstance.instance_id.in_([sender_instance_id, target_instance_id])
            )
        )
        instances = {inst.instance_id: inst for inst in result.scalars().all()}

        sender = instances.get(sender_instance_id)
        target = instances.get(target_instance_id)

        if not sender:
            raise RuntimeError(f"Sender instance {sender_instance_id} not found")

        if not target:
            raise RuntimeError(f"Target instance {target_instance_id} not found")

        # Validate sender is PM
        if sender.role != "pm":
            raise RuntimeError(f"Only PM can use contact_session (caller role: {sender.role})")

        # Validate same project
        if target.project_id != project_id:
            raise RuntimeError(
                f"Target instance {target_instance_id} belongs to different project "
                f"(expected: {project_id}, actual: {target.project_id})"
            )

        logger.info(
            f"[MESSAGING_ENGINE] Validated PM {sender_instance_id} -> {target_instance_id} in project {project_id}"
        )


async def _enqueue_with_error_notification(
    recipient_instance_id: str,
    query_msg: "QueryMessage",
    sender_instance_id: str
) -> None:
    """
    Enqueue message with error handling and sender notification.

    This wrapper handles background message delivery failures by logging
    errors and notifying the sender via SSE when delivery fails.

    Args:
        recipient_instance_id: Target instance ID
        query_msg: Message to deliver
        sender_instance_id: Sender's instance ID for error notifications
    """
    from ..services.session_executor import session_executor

    try:
        await session_executor.enqueue(recipient_instance_id, query_msg)
        logger.info(
            f"[MESSAGING_ENGINE] ✅ Message delivered to {recipient_instance_id[:8]} "
            f"from {sender_instance_id[:8]}"
        )
    except Exception as e:
        logger.error(
            f"[MESSAGING_ENGINE] ❌ Failed to deliver message to {recipient_instance_id}: {e}",
            exc_info=True
        )
        # Notify sender of delivery failure via SSE
        await sse_manager.broadcast(sender_instance_id, {
            "type": "message_delivery_failed",
            "recipient_instance_id": recipient_instance_id,
            "error": str(e),
            "timestamp": "now"
        })


async def _send_cross_session_message(
    sender_session_id: str,
    recipient_instance_id: str,
    message: str,
    priority: str = "normal"
) -> dict[str, Any]:
    """Shared engine for all cross-session messaging.

    Handles sender resolution, message envelope creation with sender_id tracking,
    and message delivery via session executor.

    Args:
        sender_session_id: Sender's Claude SDK session ID
        recipient_instance_id: Recipient's instance ID
        message: Message content
        priority: "normal" or "urgent" (urgent clears queue)

    Returns:
        Confirmation dict with content array
    """
    from ..services.session_executor import QueryMessage, QueryType
    from ..core.task_manager import get_task_manager

    # Resolve sender context (single optimized query)
    sender = await _resolve_sender_context(sender_session_id)

    logger.info(
        f"[MESSAGING_ENGINE] Message from {sender['role']} {sender['instance_id'][:8]} "
        f"to {recipient_instance_id[:8]}: {message[:80]}..."
    )

    # Create message envelope with sender tracking
    query_msg = QueryMessage(
        message=message,
        sender_role=sender["role"],
        sender_name=sender["name"],
        sender_id=sender["instance_id"],
        query_type=QueryType.INTERRUPT if priority == "urgent" else QueryType.NORMAL
    )

    # 🔥 FIRE-AND-FORGET: Dispatch message delivery to background task
    # This prevents blocking if the target session is hung or unresponsive
    task_manager = get_task_manager()
    task_manager.create_task(
        _enqueue_with_error_notification(
            recipient_instance_id=recipient_instance_id,
            query_msg=query_msg,
            sender_instance_id=sender["instance_id"]
        ),
        name=f"deliver_message_{recipient_instance_id[:8]}"
    )

    logger.info(
        f"[MESSAGING_ENGINE] 🚀 Message dispatched to background for {recipient_instance_id[:8]} "
        f"(priority: {priority})"
    )

    return {
        "success": True,
        "recipient_instance_id": recipient_instance_id,
        "sender_instance_id": sender["instance_id"],
        "status": "dispatched",
        "note": "Message delivery in progress (fire-and-forget)"
    }


# ============================================================================
# Tools for Orchestrators - Contact PM
# ============================================================================

async def _contact_pm_background(session_id: str, message: str) -> None:
    """
    Background task for PM contact with error notifications.

    Handles routing to PM and message delivery asynchronously, notifying
    the sender via SSE if any step fails.

    Args:
        session_id: Sender's Claude SDK session ID
        message: Message to send to PM
    """
    import asyncio
    from ..services.claude_client import client_manager

    sender_instance_id = None
    try:
        # Get sender instance ID for error notifications
        sender_instance_id = client_manager.get_instance_id_from_session(session_id)

        # Route to PM instance with timeout protection
        pm_instance_id = await asyncio.wait_for(
            _route_to_pm_from_session(session_id),
            timeout=10.0  # 10-second timeout for DB query
        )

        logger.info(
            f"[PM_TOOLS] 🔍 Routed {sender_instance_id[:8] if sender_instance_id else 'unknown'} -> PM {pm_instance_id[:8]}"
        )

        # Send message (this is already fire-and-forget internally)
        await _send_cross_session_message(
            sender_session_id=session_id,
            recipient_instance_id=pm_instance_id,
            message=message
        )

        logger.info(
            f"[PM_TOOLS] ✅ PM contact completed for {sender_instance_id[:8] if sender_instance_id else 'unknown'}"
        )

    except asyncio.TimeoutError:
        logger.error(
            f"[PM_TOOLS] ⏱️ Timeout routing to PM from session {session_id[:8]} (database query hung)"
        )
        if sender_instance_id:
            await sse_manager.broadcast(sender_instance_id, {
                "type": "pm_contact_failed",
                "error": "Database query timed out - system may be overloaded",
                "timestamp": "now"
            })
    except Exception as e:
        logger.error(
            f"[PM_TOOLS] ❌ Failed to contact PM from session {session_id[:8]}: {e}",
            exc_info=True
        )
        if sender_instance_id:
            await sse_manager.broadcast(sender_instance_id, {
                "type": "pm_contact_failed",
                "error": str(e),
                "timestamp": "now"
            })


@tool(
    "contact_pm",
    "Send a SHORT, CONCISE message to the PM (max 2-3 sentences) to request guidance, report status, or ask for help",
    {
        "message": str
    }  # session_id auto-injected by hook
)
async def contact_pm(args: dict[str, Any]) -> dict[str, Any]:
    """Send message to PM agent.

    IMPORTANT: Keep messages SHORT and CONCISE (2-3 sentences max).

    When to Contact PM:
    - 🚀 Starting work: Brief notification when beginning a new task
    - ✅ Completion: Report when task is done with outcome summary
    - 🚧 Blockers: Immediately report if blocked (missing info, dependencies, errors)
    - 🤔 Guidance needed: When uncertain about approach or trade-offs
    - 📊 Major milestones: Significant progress updates (e.g., 50% complete)
    - ⚠️ Errors: Critical failures or repeated errors

    Message Style Guidelines:
    - Maximum 2-3 sentences
    - Focus on actionable information only
    - Avoid verbose explanations or implementation details
    - Use bullet points for clarity when needed

    Good Examples:
    ✓ "Started implementing user authentication. Planning to use JWT tokens. Should I proceed or do you prefer OAuth?"
    ✓ "Blocked: Missing database schema for user profiles. Need this to proceed with backend API."
    ✓ "Task complete: API endpoints deployed and tested. Ready for next task."

    Bad Examples (too verbose):
    ✗ "I have analyzed the requirements and after careful consideration of various authentication methods including session-based, JWT, OAuth, and SAML, I believe that JWT tokens would be the most appropriate choice..."
    ✗ "Just wanted to let you know that I'm making progress on the feature and I've been coordinating with the frontend specialist and..."

    Args:
        message: SHORT message to send to the PM (2-3 sentences max)
        session_id: Claude SDK session ID (auto-injected by hook)

    Returns:
        Confirmation that message was sent to PM
    """
    # Get auto-injected session_id
    session_id = args.get("session_id", "")
    message = args.get("message", "")

    # Validate inputs
    if not session_id:
        return {
            "content": [{
                "type": "text",
                "text": "✗ Error: session_id is required (should be auto-injected)"
            }]
        }

    if not message:
        return {
            "content": [{
                "type": "text",
                "text": "✗ Error: message is required"
            }]
        }

    logger.info(f"[PM_TOOLS] contact_pm called: {message[:100]}...")

    # 🔥 FIRE-AND-FORGET: Dispatch PM contact to background task
    # This prevents blocking if database query hangs or PM is unresponsive
    from ..core.task_manager import get_task_manager
    task_manager = get_task_manager()
    task_manager.create_task(
        _contact_pm_background(session_id, message),
        name=f"contact_pm_{session_id[:8]}"
    )

    logger.info(f"[PM_TOOLS] 🚀 PM contact dispatched to background for session {session_id[:8]}")

    return {
        "content": [{
            "type": "text",
            "text": "✓ Message to PM dispatched\n\nYour message is being delivered to the Project Manager."
        }]
    }


# ============================================================================
# Tools for PM Only - Session Management
# ============================================================================

@tool(
    "list_team_members",
    "Get the list of available team members (specialists) for this project",
    {"project_id": str}
)
async def list_team_members(args: dict[str, Any]) -> dict[str, Any]:
    """List available team members for the project (PM only).

    Returns all character specialists that are available for assignment
    to sessions in this project.

    Args:
        project_id: The project ID to query team members for

    Returns:
        List of team members with their details
    """
    try:
        from sqlalchemy import select
        from ..models.database import Project, Character

        project_id = args.get("project_id", "")
        if not project_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: project_id is required"
                }]
            }

        logger.info(f"[PM_TOOLS] Listing team members for project {project_id}")

        async with AsyncSessionLocal() as db:
            # Get project
            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()

            if not project:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"✗ Error: Project {project_id} not found"
                    }]
                }

            team_member_ids = project.team_member_ids or []

            if not team_member_ids:
                return {
                    "content": [{
                        "type": "text",
                        "text": "⚠️ No team members configured for this project.\n\nPlease configure team members in the project settings."
                    }]
                }

            # Read character details directly from filesystem
            # (Character table in DB is just for UI customization)
            from pathlib import Path
            import yaml
            from ..core.config import settings

            # Build response
            result_lines = [f"👥 Available Team Members for {project.name}", ""]
            result_lines.append(f"Total: {len(team_member_ids)} specialists")
            result_lines.append("")

            for char_id in team_member_ids:
                char_dir = settings.characters_dir / char_id
                agent_md = char_dir / "agent.md"

                if agent_md.exists():
                    with open(agent_md) as f:
                        content = f.read()
                        # Parse frontmatter
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                frontmatter = yaml.safe_load(parts[1])
                                name = frontmatter.get("name", char_id)
                                description = frontmatter.get("description", "No description")
                                skills = frontmatter.get("skills", [])

                                result_lines.append(f"• {name} ({char_id})")
                                result_lines.append(f"  {description}")
                                if skills:
                                    # Ensure skills is a list (handle both string and list formats)
                                    if isinstance(skills, str):
                                        skills = [s.strip() for s in skills.split(',')]
                                    result_lines.append(f"  Skills: {', '.join(skills)}")
                                result_lines.append("")
                else:
                    result_lines.append(f"• {char_id} (character file not found)")
                    result_lines.append("")

            return {
                "content": [{
                    "type": "text",
                    "text": "\n".join(result_lines)
                }]
            }

    except Exception as e:
        logger.error(f"[PM_TOOLS] Error listing team members: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to list team members: {str(e)}"
            }]
        }


@tool(
    "spawn_instance",
    "Create a new agent instance with specified configuration",
    {
        "project_id": str,
        "session_description": str,
        "project_path": str,
        "specialists": list,  # List of specialist character IDs
    }
)
async def spawn_instance(args: dict[str, Any]) -> dict[str, Any]:
    """Spawn a new instance (PM only).

    Creates a new orchestrator session in the backlog. The session will not start
    until you send it a message using contact_session.

    Args:
        project_id: The project ID this session belongs to
        session_description: Short description of what the session should accomplish (metadata only, not sent to agent)
        project_path: Path to the project directory
        specialists: List of specialist character IDs to assign (required, at least 1)

    Returns:
        Created session details including session_id
    """
    try:
        # Import session components
        from backend.config.session_roles import SessionRole
        from backend.services.session_executor import session_executor, QueryMessage
        from backend.sessions import get_session_registry
        import uuid
        from pathlib import Path

        project_id = args.get("project_id", "")
        description = args.get("session_description", "")
        project_path = args.get("project_path", "")
        specialists = args.get("specialists", [])
        # Always create sessions in backlog - they activate when receiving first message
        kanban_stage = "backlog"

        # Handle specialists parameter - MCP tools may pass it in various formats
        logger.info(f"[PM_TOOLS] Raw specialists parameter: type={type(specialists)}, value={repr(specialists)}")

        if isinstance(specialists, str):
            # Try parsing as JSON first (handles ["gakki", "other"] format)
            try:
                specialists = json.loads(specialists)
                logger.info(f"[PM_TOOLS] Parsed specialists from JSON: type={type(specialists)}, value={specialists}")
            except json.JSONDecodeError:
                # If not JSON, treat as single specialist ID (handles "gakki" format)
                if specialists.strip():  # Only if non-empty string
                    specialists = [specialists.strip()]
                    logger.info(f"[PM_TOOLS] Converted single specialist string to list: {specialists}")
                else:
                    specialists = []
                    logger.warning(f"[PM_TOOLS] Empty string provided for specialists")

        # Ensure specialists is always a list
        if not isinstance(specialists, list):
            logger.warning(f"[PM_TOOLS] specialists is not a list after parsing, converting: {type(specialists)}")
            specialists = []

        logger.info(f"[PM_TOOLS] Final specialists value: type={type(specialists)}, value={specialists}")

        if not project_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: project_id is required"
                }]
            }

        if not description:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: session_description is required"
                }]
            }

        if not project_path:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: project_path is required"
                }]
            }

        if not specialists or len(specialists) == 0:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: At least one specialist is required. Please specify team members for the session."
                }]
            }

        logger.info(f"[PM_TOOLS] Spawning session for project {project_id}: {description[:100]}...")
        logger.info(f"[PM_TOOLS] Project path: {project_path}")
        logger.debug(f"[PM_TOOLS] kanban_stage: {kanban_stage}, specialists: {specialists}")

        # Generate instance ID
        instance_id = f"orchestrator-{uuid.uuid4().hex[:8]}"

        # Create session directory structure
        from ..utils.context_files import generate_session_md, setup_session_directory_structure
        session_path = str(Path(project_path) / ".sessions" / instance_id)
        setup_session_directory_structure(Path(session_path))
        logger.debug(f"[PM_TOOLS] Created session directory: {session_path}")

        # Generate SESSION.md with goal and specialists
        await generate_session_md(
            session_path=session_path,
            instance_id=instance_id,
            project_id=project_id,
            session_description=description,
            specialist_ids=specialists,
        )

        # Create session using factory
        # NOTE: For orchestrators, use session_path as working directory (where SESSION.md lives)
        logger.debug(f"[PM_TOOLS] Creating session with {len(specialists)} specialist(s)")

        # Determine role and configuration
        if len(specialists) == 1:
            # Single specialist → SpecialistSession
            role = SessionRole.SINGLE_SPECIALIST
            character_id = specialists[0]
            specialist_list = None
            logger.debug(f"[PM_TOOLS] Using SINGLE_SPECIALIST role for '{character_id}'")
        else:
            # Multiple specialists → OrchestratorSession
            role = SessionRole.ORCHESTRATOR
            character_id = None
            specialist_list = specialists
            logger.debug(f"[PM_TOOLS] Using ORCHESTRATOR role with {len(specialists)} specialists")

        # Create session via registry (ensures singleton per instance_id)
        registry = get_session_registry()
        session = await registry.get_or_create_session(
            instance_id=instance_id,
            role=role,
            project_path=session_path,  # Use session directory as working directory
            character_id=character_id,
            specialists=specialist_list,
            project_id=project_id,
        )

        logger.debug(f"[PM_TOOLS] Created/retrieved {type(session).__name__} with instance_id: {instance_id}")

        # Update database record with correct project_path and other fields
        # The session works in session_path, but DB needs project root for UI filtering
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            db_instance = result.scalar_one_or_none()
            if db_instance:
                db_instance.project_path = project_path  # Fix: Use project root, not session dir
                db_instance.kanban_stage = kanban_stage
                db_instance.session_description = description
                await db.commit()
                logger.debug(f"[PM_TOOLS] Updated project_path: {project_path}, kanban_stage: {kanban_stage}")

        # Get final session state
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            agent = result.scalar_one()

        logger.info(f"[PM_TOOLS] Created session {instance_id} in backlog (status: {agent.status})")

        result_text = f"""✓ Session created successfully in backlog!

Session ID: {instance_id}
Description: {description}
Specialists: {', '.join(specialists) if specialists else 'None'}

⚠️  Session is in backlog and idle. Use contact_session to send the first message and start execution."""

        return {
            "content": [{
                "type": "text",
                "text": result_text
            }],
            "instance_id": instance_id  # Return instance_id for frontend session jump button
        }

    except Exception as e:
        logger.error(f"[PM_TOOLS] Error spawning session: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to spawn session: {str(e)}"
            }]
        }


@tool(
    "get_project_status",
    "Query all sessions in a project grouped by kanban stage",
    {"project_id": str}
)
async def get_project_status(args: dict[str, Any]) -> dict[str, Any]:
    """Get project status (PM only).

    Returns all sessions for a project, grouped by kanban stage,
    with status, description, and timestamps.

    Args:
        project_id: The project ID to query

    Returns:
        Project status with sessions grouped by stage
    """
    try:
        project_id = args.get("project_id", "")
        if not project_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: project_id is required"
                }]
            }

        logger.info(f"[PM_TOOLS] Querying project status for {project_id}")

        # Query all sessions for this project
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBAgentInstance).where(
                    DBAgentInstance.project_id == project_id,
                    DBAgentInstance.role != "pm"  # Exclude PM session from status
                )
            )
            sessions = result.scalars().all()

        # Group by kanban stage (new 4-column layout)
        stages = {
            "backlog": [],
            "active": [],
            "waiting": [],
            "done": []
        }

        for session in sessions:
            stage = session.kanban_stage or "backlog"

            # Normalize old stages to new schema
            if stage in ["blocked", "review"]:
                stage = "waiting"

            # Determine execution status label
            execution_status = "🟢 Running" if session.status in ["working", "thinking"] else "⚪ Idle"
            if session.status == "error":
                execution_status = "🔴 Error"

            session_info = {
                "session_id": session.instance_id,
                "description": session.session_description,
                "status": session.status,
                "execution_status": execution_status,  # Human-readable execution state
                "role": session.role,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "specialists": session.selected_specialists or []
            }

            if stage in stages:
                stages[stage].append(session_info)
            else:
                # Default to backlog if unknown stage
                stages["backlog"].append(session_info)

        total_sessions = len(sessions)

        logger.info(f"[PM_TOOLS] Project {project_id}: {total_sessions} total sessions")

        # Format response as readable text
        result_lines = [f"📊 Project Status for {project_id}", ""]
        result_lines.append(f"Total Sessions: {total_sessions}")
        result_lines.append("")

        for stage, items in stages.items():
            if items:
                result_lines.append(f"{stage.upper()} ({len(items)}):")
                for session in items:
                    # Show full session_id for tools, truncate description for readability
                    session_id = session['session_id']
                    description = session['description'] or "No description"
                    # Truncate description to 80 chars
                    if len(description) > 80:
                        description = description[:77] + "..."

                    execution_status = session['execution_status']
                    status = session['status']
                    role = session['role']
                    specialists = session.get('specialists', [])
                    specialists_str = f" [{', '.join(specialists)}]" if specialists else ""

                    result_lines.append(f"  • ID: {session_id}")
                    result_lines.append(f"    Description: {description}")
                    result_lines.append(f"    Execution: {execution_status} | Kanban Status: {status} | Role: {role}{specialists_str}")
                result_lines.append("")

        if total_sessions == 0:
            result_lines.append("No sessions found in this project.")

        return {
            "content": [{
                "type": "text",
                "text": "\n".join(result_lines)
            }]
        }

    except Exception as e:
        logger.error(f"[PM_TOOLS] Error getting project status: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to get project status: {str(e)}"
            }]
        }


@tool(
    "update_instance_stage",
    "Move an instance to waiting or done stage",
    {"project_id": str, "instance_id": str, "new_stage": str}
)
async def update_instance_stage(args: dict[str, Any]) -> dict[str, Any]:
    """Update instance's kanban stage (PM only).

    Mark sessions as waiting (paused/blocked) or done (completed).
    Sessions cannot be manually moved to 'active' - they activate automatically when receiving messages.

    Args:
        project_id: The project ID this instance belongs to
        instance_id: ID of the instance to update
        new_stage: Target stage ('waiting' or 'done')

    Returns:
        Success status

    Note:
        - Moving to 'waiting' does NOT auto-cancel - use cancel_instance for that
        - Sessions start in 'backlog' and activate when you send them messages
    """
    try:
        project_id = args.get("project_id", "")
        instance_id = args.get("instance_id", "")
        new_stage = args.get("new_stage", "")

        if not project_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: project_id is required"
                }]
            }

        if not instance_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: instance_id is required"
                }]
            }

        # Validate stage - only allow waiting and done
        # Sessions start in backlog and activate automatically via contact_session
        valid_stages = ["waiting", "done"]
        if new_stage not in valid_stages:
            return {
                "content": [{
                    "type": "text",
                    "text": f"✗ Error: Invalid stage '{new_stage}'. Can only move to: {', '.join(valid_stages)}\n\n" +
                           "Sessions start in 'backlog' and activate automatically when you send messages via contact_session."
                }]
            }

        logger.info(f"[PM_TOOLS] Moving instance {instance_id} to {new_stage} in project {project_id}")

        # Update session stage
        async with AsyncSessionLocal() as db:
            # Get session
            result = await db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"✗ Error: Instance {instance_id} not found"
                    }]
                }

            # Validate session belongs to same project
            if session.project_id != project_id:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"✗ Error: Instance {instance_id} belongs to different project"
                    }]
                }

            # Don't allow moving PM sessions
            if session.role == "pm":
                return {
                    "content": [{
                        "type": "text",
                        "text": "✗ Error: Cannot move PM session through kanban stages"
                    }]
                }

            old_stage = session.kanban_stage
            session.kanban_stage = new_stage
            await db.commit()

        logger.info(f"[PM_TOOLS] Instance {instance_id} moved: {old_stage} -> {new_stage}")

        return {
            "content": [{
                "type": "text",
                "text": f"✓ Instance {instance_id[:8]} moved from {old_stage} to {new_stage}"
            }]
        }

    except Exception as e:
        logger.error(f"[PM_TOOLS] Error updating session stage: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to update session stage: {str(e)}"
            }]
        }


async def _contact_session_background(
    session_id: str,
    project_id: str,
    instance_id: str,
    message: str
) -> None:
    """
    Background task for session contact with error notifications.

    Handles validation and message delivery asynchronously, notifying
    the sender via SSE if any step fails.

    Args:
        session_id: Sender's Claude SDK session ID (PM)
        project_id: Project ID for validation
        instance_id: Target instance ID
        message: Message to send
    """
    import asyncio
    from ..services.claude_client import client_manager

    sender_instance_id = None
    try:
        # Get sender instance ID for error notifications
        sender_instance_id = client_manager.get_instance_id_from_session(session_id)

        # Validate PM permissions and same-project routing with timeout
        await asyncio.wait_for(
            _validate_pm_routing(session_id, project_id, instance_id),
            timeout=10.0
        )

        logger.info(
            f"[PM_TOOLS] ✅ Validated PM {sender_instance_id[:8] if sender_instance_id else 'unknown'} -> {instance_id[:8]}"
        )

        # Send message (this is already fire-and-forget internally)
        await _send_cross_session_message(
            sender_session_id=session_id,
            recipient_instance_id=instance_id,
            message=message
        )

        logger.info(
            f"[PM_TOOLS] ✅ Session contact completed: {sender_instance_id[:8] if sender_instance_id else 'unknown'} -> {instance_id[:8]}"
        )

    except asyncio.TimeoutError:
        logger.error(
            f"[PM_TOOLS] ⏱️ Timeout validating PM routing (database query hung)"
        )
        if sender_instance_id:
            await sse_manager.broadcast(sender_instance_id, {
                "type": "session_contact_failed",
                "target_instance_id": instance_id,
                "error": "Database query timed out - system may be overloaded",
                "timestamp": "now"
            })
    except Exception as e:
        logger.error(
            f"[PM_TOOLS] ❌ Failed to contact session {instance_id}: {e}",
            exc_info=True
        )
        if sender_instance_id:
            await sse_manager.broadcast(sender_instance_id, {
                "type": "session_contact_failed",
                "target_instance_id": instance_id,
                "error": str(e),
                "timestamp": "now"
            })


@tool(
    "contact_session",
    "Send a message to a specific agent session to provide guidance, assign tasks, or reactivate idle sessions",
    {"project_id": str, "instance_id": str, "message": str}
)
async def contact_session(args: dict[str, Any]) -> dict[str, Any]:
    """Send message to specific session (PM only).

    Works with instances in ANY status (active, idle, or completed)
    Use for: continuing work, providing context, requesting refinements, or course corrections.

    Args:
        project_id: The project ID this instance belongs to
        instance_id: ID of the target instance (from list_instances)
        message: Message to send (will appear as user input to the instance)
        session_id: Claude SDK session ID (auto-injected by hook)

    Returns:
        Delivery confirmation with queue status
    """
    try:
        session_id = args.get("session_id", "")
        project_id = args.get("project_id", "")
        instance_id = args.get("instance_id", "")
        message = args.get("message", "")

        # Validate inputs
        if not session_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: session_id is required (should be auto-injected)"
                }]
            }

        if not project_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: project_id is required"
                }]
            }

        if not instance_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: instance_id is required"
                }]
            }

        if not message:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: message is required"
                }]
            }

        logger.info(f"[PM_TOOLS] Sending message to instance {instance_id} in project {project_id}: {message[:100]}...")

        # 🔥 FIRE-AND-FORGET: Dispatch session contact to background task
        # This prevents blocking if database query hangs or target is unresponsive
        from ..core.task_manager import get_task_manager
        task_manager = get_task_manager()
        task_manager.create_task(
            _contact_session_background(session_id, project_id, instance_id, message),
            name=f"contact_session_{instance_id[:8]}"
        )

        logger.info(f"[PM_TOOLS] 🚀 Session contact dispatched to background for {instance_id[:8]}")

        return {
            "content": [{
                "type": "text",
                "text": f"✓ Message to instance {instance_id[:8]} dispatched\n\nYour message is being delivered."
            }]
        }

    except Exception as e:
        logger.error(f"[PM_TOOLS] Error dispatching message to session: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to dispatch message: {str(e)}"
            }]
        }


@tool(
    "cancel_instance",
    "Cancel and optionally delete an instance",
    {"project_id": str, "instance_id": str, "reason": str}
)
async def cancel_instance(args: dict[str, Any]) -> dict[str, Any]:
    """Cancel an instance (PM only).

    Stop a running instance and mark it as cancelled.
    Useful for duplicate work or when priorities change.

    Args:
        project_id: The project ID this instance belongs to
        instance_id: ID of the instance to cancel
        reason: Reason for cancellation (for logging)

    Returns:
        Cancellation confirmation
    """
    try:
        # Lazy import to avoid circular dependency
        from ..services.claude_client import client_manager

        project_id = args.get("project_id", "")
        instance_id = args.get("instance_id", "")
        reason = args.get("reason", "Cancelled by PM")

        if not project_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: project_id is required"
                }]
            }

        if not instance_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: instance_id is required"
                }]
            }

        logger.info(f"[PM_TOOLS] Cancelling instance {instance_id} in project {project_id}: {reason}")

        # Validate session exists and belongs to same project
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"✗ Error: Instance {instance_id} not found"
                    }]
                }

            if session.project_id != project_id:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"✗ Error: Instance {instance_id} belongs to different project"
                    }]
                }

            # Don't allow cancelling PM instances
            if session.role == "pm":
                return {
                    "content": [{
                        "type": "text",
                        "text": "✗ Error: Cannot cancel PM instance using this tool"
                    }]
                }

            # Mark as cancelled in database
            session.status = "cancelled"
            await db.commit()

        # Try to interrupt the running client (if it exists)
        try:
            client = await client_manager.get_client(instance_id)
            if client:
                await client.interrupt()
                logger.info(f"[PM_TOOLS] Interrupted running client for instance {instance_id}")
        except Exception as e:
            # Log but don't fail if client interrupt fails
            logger.warning(f"[PM_TOOLS] Could not interrupt client: {e}")

        logger.info(f"[PM_TOOLS] Instance {instance_id} cancelled: {reason}")

        return {
            "content": [{
                "type": "text",
                "text": f"✓ Instance {instance_id[:8]} cancelled successfully\n\nReason: {reason}"
            }]
        }

    except Exception as e:
        logger.error(f"[PM_TOOLS] Error cancelling session: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to cancel session: {str(e)}"
            }]
        }


@tool(
    "remind",
    "Schedule a wake-up call to remind yourself about something after a delay. Useful for checking on long-running processes.",
    {"delay_seconds": int, "message": str}  # session_id auto-injected by hook
)
async def remind(args: dict[str, Any]) -> dict[str, Any]:
    """Schedule a reminder message to be sent back to this session after a delay.

    Use this when you need to check on something later, such as:
    - Waiting for a build to complete
    - Checking deployment status after some time
    - Following up on a long-running task
    - Polling for external process completion

    Args:
        delay_seconds: How many seconds to wait before sending the reminder
        message: The reminder message to send back to yourself
        session_id: Claude SDK session ID (auto-injected by hook)

    Returns:
        Confirmation that reminder is scheduled
    """
    import asyncio
    from ..core.task_manager import get_task_manager
    from ..services.claude_client import client_manager

    try:
        delay_seconds = args.get("delay_seconds", 60)
        message = args.get("message", "Reminder: Check status")
        session_id = args.get("session_id", "")

        # Validate delay
        if delay_seconds < 1:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Delay must be at least 1 second"
                }]
            }

        if delay_seconds > 86400:  # 24 hours
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Delay cannot exceed 24 hours (86400 seconds)"
                }]
            }

        # Validate session_id is provided (should be auto-injected by hook)
        if not session_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ session_id is required (should be auto-injected)"
                }]
            }

        # Reverse lookup: session_id -> instance_id
        instance_id = client_manager.get_instance_id_from_session(session_id)
        if not instance_id:
            return {
                "content": [{
                    "type": "text",
                    "text": f"✗ Could not find instance for session_id: {session_id}"
                }]
            }

        logger.info(f"[REMIND] Scheduling reminder for session {session_id} -> instance {instance_id}")

        # Schedule the reminder
        async def send_reminder():
            """Background task that waits and sends the reminder."""
            try:
                logger.info(f"[REMIND] Waiting {delay_seconds}s before sending reminder to {instance_id}")
                await asyncio.sleep(delay_seconds)

                logger.info(f"[REMIND] Sending reminder to {instance_id}: {message[:50]}...")

                # Queue the reminder message through session executor to ensure serial execution
                # This prevents the reminder from interrupting ongoing streaming
                from ..services.session_executor import session_executor, QueryMessage, QueryType

                query_msg = QueryMessage(
                    message=f"⏰ **Reminder**\n\n{message}",
                    sender_role="system",
                    sender_name="Reminder",
                    query_type=QueryType.NORMAL  # Queue normally, don't interrupt
                )

                # Check queue status before enqueueing (for logging)
                is_processing = session_executor.is_processing(instance_id)
                queue_size = session_executor.get_queue_size(instance_id)
                logger.info(
                    f"[REMIND] Queueing reminder for {instance_id} "
                    f"(currently processing: {is_processing}, queue size: {queue_size})"
                )

                await session_executor.enqueue(instance_id, query_msg)
                logger.info(f"[REMIND] Reminder queued for {instance_id}")

            except Exception as e:
                logger.error(f"[REMIND] Failed to queue reminder: {e}", exc_info=True)

        # Create background task
        task_manager = get_task_manager()
        task_manager.create_task(
            send_reminder(),
            name=f"remind_{instance_id}_{delay_seconds}s"
        )

        logger.info(
            f"[PM_TOOLS] Scheduled reminder for instance {instance_id} "
            f"in {delay_seconds}s: {message[:50]}..."
        )

        # Human-readable time format
        if delay_seconds < 60:
            time_str = f"{delay_seconds} second{'s' if delay_seconds != 1 else ''}"
        elif delay_seconds < 3600:
            minutes = delay_seconds // 60
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = delay_seconds // 3600
            minutes = (delay_seconds % 3600) // 60
            time_str = f"{hours}h {minutes}m" if minutes > 0 else f"{hours} hour{'s' if hours != 1 else ''}"

        return {
            "content": [{
                "type": "text",
                "text": (
                    f"⏰ Reminder scheduled for {time_str} from now\n\n"
                    f"Message: {message}\n\n"
                    f"You'll receive this reminder automatically. Continue with other work."
                )
            }]
        }

    except Exception as e:
        logger.error(f"[PM_TOOLS] Error scheduling reminder: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to schedule reminder: {str(e)}"
            }]
        }


@tool(
    "show_file",
    "Display a file to the user with a preview card. Shows image thumbnails for images, file icons for other types.",
    {"path": str}
)
async def show_file(args: dict[str, Any]) -> dict[str, Any]:
    """Display a file to the user by creating a preview card in the frontend.

    This tool validates that the file exists and marks it for display. The frontend
    will show a thumbnail for images or a file type icon for other files. Users can
    click to view the full file content.

    Use this when you want to:
    - Show a file you've created (image, document, code, etc.)
    - Present results of file generation or manipulation
    - Let the user review a file before taking further action

    Args:
        path: Path to the file to display (relative or absolute)

    Returns:
        Success confirmation that file will be displayed
    """
    import os
    from pathlib import Path

    try:
        file_path = args.get("path", "")

        if not file_path:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: No file path provided"
                }]
            }

        # Validate file exists
        if not os.path.exists(file_path):
            return {
                "content": [{
                    "type": "text",
                    "text": f"✗ Error: File not found: {file_path}"
                }]
            }

        # Validate it's a file (not a directory)
        if not os.path.isfile(file_path):
            return {
                "content": [{
                    "type": "text",
                    "text": f"✗ Error: Path is not a file: {file_path}"
                }]
            }

        # Get file info for response
        file_size = os.path.getsize(file_path)
        file_name = Path(file_path).name

        # Format file size
        if file_size < 1024:
            size_str = f"{file_size} bytes"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"

        logger.info(f"[SHOW_FILE] Displaying file: {file_path} ({size_str})")

        # Return empty response - frontend will detect this tool call and render preview card
        # No need for text output since the file preview is shown inline
        return {
            "content": [{
                "type": "text",
                "text": ""
            }]
        }

    except Exception as e:
        logger.error(f"[SHOW_FILE] Error displaying file: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to display file: {str(e)}"
            }]
        }


@tool(
    "notify_user",
    (
        "Send a desktop notification to the user. Use this when you need the user's immediate "
        "attention or want to notify them about important updates, decisions needed, blockers, "
        "or task completions. The notification will appear as a system notification on their desktop."
    ),
    {
        "message": str,
        "title": str,
        "priority": str,
        "session_id": str
    }
)
async def notify_user(args: dict[str, Any]) -> dict[str, Any]:
    """Send a desktop notification to the user.

    Args:
        message: Notification message content
        title: Notification title (default: 'PM Notification')
        priority: Priority level ('low', 'normal', 'high', default: 'normal')
        session_id: Claude SDK session ID (auto-injected by hook)

    Returns:
        Success confirmation
    """
    from ..services.claude_client import client_manager

    try:
        message = args.get("message", "")
        title = args.get("title", "PM Notification")
        priority = args.get("priority", "normal")
        session_id = args.get("session_id")

        if not message:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: message parameter is required"
                }]
            }

        if not session_id:
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Error: session_id is required (should be auto-injected)"
                }]
            }

        # Validate priority
        if priority not in ["low", "normal", "high"]:
            priority = "normal"

        # Get instance_id from session_id using client_manager
        instance_id = client_manager.get_instance_id_from_session(session_id)

        if not instance_id:
            logger.warning(f"[NOTIFY_USER] Could not resolve instance_id from session_id: {session_id}")
            return {
                "content": [{
                    "type": "text",
                    "text": "✗ Failed to send notification: session not found"
                }]
            }

        # Get project name from instance
        project_name = "KumiAI"
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            instance = result.scalar_one_or_none()
            if instance and instance.project_id:
                from ..models.database import Project
                project_result = await db.execute(
                    select(Project).where(Project.id == instance.project_id)
                )
                project = project_result.scalar_one_or_none()
                if project:
                    project_name = project.name

        # Broadcast notification event via SSE
        notification_event = {
            "type": "user_notification",
            "title": title,
            "message": message,
            "project_name": project_name,
            "priority": priority,
            "timestamp": "now"  # Will be enriched by SSE manager
        }

        await sse_manager.broadcast(instance_id, notification_event)

        logger.info(f"[NOTIFY_USER] Sent notification to user: {title} - {message}")

        return {
            "content": [{
                "type": "text",
                "text": f"✓ Desktop notification sent to user"
            }]
        }

    except Exception as e:
        logger.error(f"[NOTIFY_USER] Error sending notification: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to send notification: {str(e)}"
            }]
        }


# ============================================================================
# Tool Collections
# ============================================================================

# Tools for PM agents (full project management capabilities)
# Note: remind is in common_tools (available to all sessions), not duplicated here
PM_MANAGEMENT_TOOLS = [
    list_team_members,
    spawn_instance,
    get_project_status,
    update_instance_stage,
    contact_session,
    cancel_instance,
    notify_user
]

# All PM-related tools (contact_pm is now in kumiAI server for orchestrators)
ALL_PM_TOOLS = [contact_pm] + PM_MANAGEMENT_TOOLS
