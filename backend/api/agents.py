"""Session API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json
import asyncio
import logging

from ..core.database import get_db
from ..core.task_manager import get_task_manager
from ..core.exceptions import (
    SessionNotFoundError,
    InvalidRequestError,
    SessionInitializationError,
)
from ..services.agent_service import AgentService
from ..services.message_service import MessageService

logger = logging.getLogger(__name__)
from ..models.schemas import (
    AgentInstance,
    SpawnAgentRequest,
    UpdateAgentStageRequest,
    SessionMessage,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/launch", response_model=AgentInstance, status_code=201)
async def launch_session(
    request: SpawnAgentRequest, db: AsyncSession = Depends(get_db)
):
    """
    Launch a new session using unified SessionFactory.

    Migrated from legacy AgentService to use SessionFactory directly.
    """
    from backend.config.session_roles import SessionRole
    from backend.sessions import get_session_registry
    from backend.models.database import AgentInstance as DBAgentInstance, DEFAULT_PROJECT_ID
    from backend.models.schemas import AgentCharacter
    from datetime import datetime
    from pathlib import Path
    import uuid

    print(f"[API] Received launch request:")
    print(f"[API]   team_member_ids: {request.team_member_ids}")
    print(f"[API]   project_path: {request.project_path}")
    print(f"[API]   session_description: {request.session_description[:50]}...")
    print(f"[API]   role: {request.role}")

    # Parse role
    try:
        role = SessionRole(request.role or "orchestrator")
    except ValueError:
        raise InvalidRequestError(f"Invalid role: {request.role}", field="role")

    # Use provided project_id or default
    project_id = request.project_id or DEFAULT_PROJECT_ID

    # Ensure project directory exists
    project_path = Path(request.project_path)
    project_path.mkdir(parents=True, exist_ok=True)

    # Generate unified instance_id for all session types (except assistants which use deterministic IDs)
    if role not in (SessionRole.CHARACTER_ASSISTANT, SessionRole.SKILL_ASSISTANT):
        instance_id = f"session-{uuid.uuid4().hex[:8]}"
    # else: instance_id will be set in role-specific blocks below

    # Determine character_id and specialists based on role
    character_id = None
    specialists = None
    session_path = str(project_path)

    if role == SessionRole.SINGLE_SPECIALIST:
        # Single specialist - create session in .sessions/ subdirectory (consistent with orchestrator)
        if request.team_member_ids and len(request.team_member_ids) >= 1:
            character_id = request.team_member_ids[0]
        session_path = str(project_path / ".sessions" / instance_id)

        from backend.utils.context_files import generate_session_md, setup_session_directory_structure
        setup_session_directory_structure(Path(session_path))
        await generate_session_md(
            session_path=session_path,
            instance_id=instance_id,
            project_id=project_id,
            session_description=request.session_description,
            specialist_ids=[character_id] if character_id else [],
        )
    elif role == SessionRole.ORCHESTRATOR:
        # Orchestrator with specialists
        specialists = request.team_member_ids
        # Create session directory for orchestrators
        session_path = str(project_path / ".sessions" / instance_id)

        from backend.utils.context_files import generate_session_md, setup_session_directory_structure
        setup_session_directory_structure(Path(session_path))
        await generate_session_md(
            session_path=session_path,
            instance_id=instance_id,
            project_id=project_id,
            session_description=request.session_description,
            specialist_ids=specialists,
        )
    elif role == SessionRole.CHARACTER_ASSISTANT:
        # Character assistant - single persistent session at library root
        from backend.core.config import settings
        session_path = str(settings.characters_dir)
        instance_id = "character_assistant"
        # No character_id needed - works at library level

    elif role == SessionRole.SKILL_ASSISTANT:
        # Skill assistant - single persistent session at library root
        from backend.core.config import settings
        session_path = str(settings.skills_dir)
        instance_id = "skill_assistant"
        # No team members needed - works at library level
    elif role == SessionRole.PM:
        # PM session
        # Generate PROJECT.md for PM
        from backend.utils.context_files import generate_project_md
        from backend.models.database import Project
        from sqlalchemy import select

        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project:
            character_id = project.pm_id
            await generate_project_md(
                project_path=str(project_path),
                project_id=project_id,
                project_name=project.name,
                project_description=project.description,
                team_member_ids=project.team_member_ids,
                pm_character_id=project.pm_id,
            )

    print(f"[API] Creating session via SessionFactory:")
    print(f"[API]   instance_id: {instance_id}")
    print(f"[API]   role: {role.value}")
    print(f"[API]   character_id: {character_id}")
    print(f"[API]   specialists: {specialists}")
    print(f"[API]   session_path: {session_path}")

    # Create stub database record immediately so frontend can see it
    # This will be updated when background initialization completes
    from backend.models.database import AgentInstance as DBAgentInstance
    kanban_stage = "backlog"

    stub_record = DBAgentInstance(
        instance_id=instance_id,
        session_id=None,  # Will be set after initialization
        character_id=character_id,
        project_id=project_id,
        project_path=session_path,
        role=role.value,
        status="initializing",  # Special status to indicate background init in progress
        session_description=request.session_description,
        kanban_stage=kanban_stage,
        actual_tools=[],
        actual_mcp_servers=[],
    )
    db.add(stub_record)
    await db.commit()
    logger.info(f"Created stub database record for session {instance_id}")

    # Schedule session creation in background (non-blocking)
    # This prevents slow/hung session initialization from blocking the API response
    from backend.core.task_manager import get_task_manager
    task_manager = get_task_manager()

    async def create_session_background():
        """Background task to create session"""
        try:
            registry = get_session_registry()
            session = await registry.get_or_create_session(
                instance_id=instance_id,
                role=role,
                project_path=session_path,
                character_id=character_id,
                specialists=specialists,
                project_id=project_id,
                model=request.model or "sonnet",
            )
            print(f"[API] Session created/retrieved:")
            print(f"[API]   instance_id: {instance_id}")
            print(f"[API]   claude_session_id: {session.session_id}")
        except Exception as e:
            logger.error(f"Background session creation failed for {instance_id}: {e}")
            # Update instance status to error
            from backend.core.database import AsyncSessionLocal
            from backend.models.database import AgentInstance
            from sqlalchemy import update
            async with AsyncSessionLocal() as db_error:
                await db_error.execute(
                    update(AgentInstance)
                    .where(AgentInstance.instance_id == instance_id)
                    .values(status="error")
                )
                await db_error.commit()

    task_manager.create_task(
        create_session_background(),
        name=f"create_session_{instance_id}"
    )
    logger.info(f"Session creation scheduled in background for {instance_id}")

    # Update database record with session_description and kanban_stage
    # Always create sessions in backlog - they activate when receiving first message
    kanban_stage = "backlog"
    from backend.models.database import AgentInstance as DBAgentInstance
    from sqlalchemy import select

    result = await db.execute(
        select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
    )
    db_instance = result.scalar_one_or_none()
    if db_instance:
        db_instance.session_description = request.session_description
        db_instance.kanban_stage = kanban_stage
        await db.commit()
        print(f"[API] Updated session_description: {request.session_description[:50]}...")
        print(f"[API] Session created in backlog - use contact_session to start")

    # Return agent instance
    service = AgentService(db)
    agent = await service.get_agent(instance_id)

    if not agent:
        raise SessionInitializationError("Failed to retrieve created session", instance_id=instance_id)

    return agent


@router.get("", response_model=list[AgentInstance])
async def list_sessions(
    project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)
):
    """Get all active sessions, optionally filtered by project_id."""
    service = AgentService(db)
    return await service.list_agents(project_id=project_id)


@router.get("/{instance_id}", response_model=AgentInstance)
async def get_session(instance_id: str, db: AsyncSession = Depends(get_db)):
    """Get specific session."""
    service = AgentService(db)
    agent = await service.get_agent(instance_id)

    if not agent:
        raise SessionNotFoundError(instance_id)

    return agent


@router.get("/{instance_id}/messages", response_model=list[SessionMessage])
async def get_session_messages(
    instance_id: str,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get message history for a session."""
    service = MessageService(db)
    messages = await service.get_messages(instance_id, limit=limit)
    return messages


@router.get("/{instance_id}/stream")
async def stream_session_events(instance_id: str, db: AsyncSession = Depends(get_db)):
    """
    SSE endpoint for real-time session events.

    This endpoint ONLY broadcasts events (status_change, result, etc.).
    To send messages, use POST /sessions/{id}/message instead.
    """
    import logging
    from ..services.sse_manager import sse_manager

    logger = logging.getLogger(__name__)

    # Validate session exists
    service = AgentService(db)
    agent = await service.get_agent(instance_id)
    if not agent:
        raise SessionNotFoundError(instance_id)

    logger.info(f"[SSE] Client connecting to instance {instance_id}")

    async def event_generator():
        """Generate SSE events from sse_manager"""
        queue = asyncio.Queue()
        await sse_manager.register(instance_id, queue)

        try:
            # Send initial status event so frontend knows current state
            # This prevents desync when client reconnects after missing status updates
            from datetime import datetime
            initial_status_event = {
                "type": "status_change",
                "status": agent.status or "idle",
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"data: {json.dumps(initial_status_event)}\n\n"
            logger.info(f"[SSE] Sent initial status '{agent.status}' to client for {instance_id}")

            while True:
                try:
                    # Wait for events from sse_manager with timeout
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"[SSE] Client disconnected from instance {instance_id}")
        finally:
            await sse_manager.unregister(instance_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{instance_id}/message", status_code=202)
async def send_message_to_session(instance_id: str, message: dict, db: AsyncSession = Depends(get_db)):
    """
    Send a message to the session (with automatic queueing).

    Messages are automatically queued if the session is busy. Multiple messages
    sent while processing are batched together for efficient execution.

    Request body:
    {
        "content": "message text",
        "query_type": "normal" | "interrupt",  // optional, defaults to "normal"
        "sender_role": "user" | "pm" | "orchestrator",  // optional, defaults to "user"
        "sender_name": "Display Name"  // optional
    }

    Returns 202 Accepted immediately with queue status.
    """
    import logging
    from ..services.session_executor import session_executor, QueryMessage, QueryType

    logger = logging.getLogger(__name__)

    content = message.get('content', '')
    query_type_str = message.get('query_type', 'normal')
    sender_role = message.get('sender_role', 'user')
    sender_name = message.get('sender_name')

    logger.info(f"[MESSAGE] Sending message for instance {instance_id} (type: {query_type_str}, sender: {sender_role}): {content[:50]}...")

    # Validate session exists
    service = AgentService(db)
    agent = await service.get_agent(instance_id)
    if not agent:
        raise SessionNotFoundError(instance_id)

    try:
        # Create query message with sender attribution
        query_msg = QueryMessage(
            message=content,
            sender_role=sender_role,
            sender_name=sender_name,
            query_type=QueryType.INTERRUPT if query_type_str == "interrupt" else QueryType.NORMAL
        )

        # Enqueue message (will trigger execution if not busy, or queue if busy)
        await session_executor.enqueue(instance_id, query_msg)

        # Return queue status
        queue_status = {
            "status": "queued",
            "queue_size": session_executor.get_queue_size(instance_id),
            "is_processing": session_executor.is_processing(instance_id)
        }

        logger.info(f"[MESSAGE] Message queued for instance {instance_id}: {queue_status}")
        return queue_status

    except Exception as e:
        logger.error(f"[MESSAGE] Failed to process message for instance {instance_id}: {e}", exc_info=True)
        from ..core.exceptions import AppException
        from fastapi import status
        raise AppException(
            message=f"Failed to process message: {str(e)}",
            code="MESSAGE_PROCESSING_FAILED",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"instance_id": instance_id}
        )


@router.get("/{instance_id}/queue-status")
async def get_queue_status(instance_id: str):
    """Get current queue status for an instance."""
    from ..services.session_executor import session_executor

    return {
        "queue_size": session_executor.get_queue_size(instance_id),
        "is_processing": session_executor.is_processing(instance_id)
    }


@router.get("/{instance_id}/status")
async def get_session_status(instance_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get current session status from in-memory cache or database.

    Returns:
        {"status": "idle"|"working"|"error"|"cancelled", "instance_id": str}
    """
    from ..sessions import get_session_registry

    # Try to get status from active session first (in-memory)
    registry = get_session_registry()
    session = registry.get_session(instance_id)

    if session and hasattr(session, '_current_status'):
        # Return in-memory status (most up-to-date)
        return {
            "status": session._current_status,
            "instance_id": instance_id,
            "source": "memory"
        }

    # Fall back to database
    service = AgentService(db)
    agent = await service.get_agent(instance_id)

    if not agent:
        raise SessionNotFoundError(instance_id)

    return {
        "status": agent.status,
        "instance_id": instance_id,
        "source": "database"
    }


@router.post("/{instance_id}/cancel", status_code=204)
async def cancel_session(instance_id: str, db: AsyncSession = Depends(get_db)):
    """Cancel a running session by sending an interrupt signal."""
    from ..services.session_executor import session_executor
    from ..sessions import get_session_registry
    import logging
    logger = logging.getLogger(__name__)

    # Validate session exists in database
    service = AgentService(db)
    agent = await service.get_agent(instance_id)
    if not agent:
        raise SessionNotFoundError(instance_id)

    # Get session from registry (if active)
    registry = get_session_registry()
    session = registry.get_session(instance_id)

    # Signal interrupt via session_executor (works even if session not in registry yet)
    session_executor.signal_interrupt(instance_id)
    logger.info(f"[API] Sent interrupt signal for instance {instance_id}")

    # If session is active in registry, also call cancel directly
    if session:
        await session.cancel()
        logger.info(f"[API] Called cancel() on active session {instance_id}")


@router.patch("/{instance_id}/stage", status_code=204)
async def update_session_stage(
    instance_id: str,
    request: UpdateAgentStageRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update session's kanban stage.

    Only allows moving sessions to 'waiting' or 'done'.
    Sessions start in 'backlog' and activate automatically when receiving messages.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Get session info
    service = AgentService(db)
    agent = await service.get_agent(instance_id)

    if not agent:
        raise SessionNotFoundError(instance_id)

    # Validate stage - only allow waiting and done
    valid_stages = ["waiting", "done"]
    if request.stage not in valid_stages:
        raise InvalidRequestError(
            f"Invalid stage '{request.stage}'. Can only move to: {', '.join(valid_stages)}",
            field="stage"
        )

    # Update kanban stage in database
    updated = await service.update_agent_stage(instance_id, request.stage)

    if not updated:
        raise SessionNotFoundError(instance_id)

    logger.info(f"[API] Session {instance_id} moved to {request.stage}")


@router.delete("/{instance_id}", status_code=204)
async def delete_session(instance_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a session instance."""
    service = AgentService(db)
    deleted = await service.delete_agent(instance_id)

    if not deleted:
        raise SessionNotFoundError(instance_id)


@router.post("/skill-assistant/recreate", status_code=200)
async def recreate_skill_assistant(db: AsyncSession = Depends(get_db)):
    """Recreate the skill assistant session.

    This deletes the existing skill assistant session and creates a fresh one.
    Useful when the session is in a broken state (e.g., conversation not found).
    """
    from sqlalchemy import select
    from ..models.database import AgentInstance as DBAgentInstance
    from ..core.database import AsyncSessionLocal
    from ..sessions import get_session_registry
    from backend.config.session_roles import SessionRole
    from ..core.config import settings

    logger.info("Recreating skill assistant session")

    instance_id = "skill_assistant"

    # Delete existing skill assistant session
    try:
        # Find and delete from database
        async with AsyncSessionLocal() as cleanup_db:
            result = await cleanup_db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            existing_session = result.scalar_one_or_none()

            if existing_session:
                logger.info(f"Found existing skill assistant session: {instance_id}")

                # Remove from registry first
                registry = get_session_registry()
                removed = registry.remove_session(instance_id)
                if removed:
                    logger.info(f"Removed skill assistant from registry: {instance_id}")
                else:
                    logger.debug(f"Skill assistant not in registry (already cleaned up): {instance_id}")

                # Delete from database (cascade will handle messages)
                await cleanup_db.delete(existing_session)
                await cleanup_db.commit()
                logger.info(f"Deleted skill assistant from database: {instance_id}")
            else:
                logger.info("No existing skill assistant session found")

        # Create fresh skill assistant session in background
        from ..core.task_manager import get_task_manager

        async def create_skill_assistant():
            """Background task to create skill assistant session."""
            try:
                from ..sessions.session_context import SessionContext

                registry = get_session_registry()

                # Create session context
                context = SessionContext(
                    instance_id=instance_id,
                    session_id=None,  # Will be created fresh
                    character_id="skill_assistant",
                    specialists=None,
                    project_id=None,
                    project_path=str(settings.skills_dir),
                    model=None
                )

                # Create new session via registry
                logger.info(f"Creating fresh skill assistant session: {instance_id}")
                session = await registry.get_or_create_session(
                    context=context,
                    role=SessionRole.SKILL_ASSISTANT
                )

                logger.info(f"✓ Skill assistant session recreated: {instance_id}")

            except Exception as e:
                logger.error(f"Failed to create skill assistant session: {e}", exc_info=True)

        # Schedule background task
        task_manager = get_task_manager()
        task_manager.create_task(
            create_skill_assistant(),
            name=f"recreate_skill_assistant"
        )

        return {
            "status": "success",
            "message": "Skill assistant session recreation initiated",
            "instance_id": instance_id
        }

    except Exception as e:
        logger.error(f"Failed to recreate skill assistant: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to recreate skill assistant: {str(e)}"
        )


@router.post("/character-assistant/recreate", status_code=200)
async def recreate_character_assistant(db: AsyncSession = Depends(get_db)):
    """Recreate the character assistant session.

    This deletes the existing character assistant session and creates a fresh one.
    Useful when the session is in a broken state (e.g., conversation not found).
    """
    from sqlalchemy import select
    from ..models.database import AgentInstance as DBAgentInstance
    from ..core.database import AsyncSessionLocal
    from ..sessions import get_session_registry
    from backend.config.session_roles import SessionRole
    from ..core.config import settings

    logger.info("Recreating character assistant session")

    instance_id = "character_assistant"

    # Delete existing character assistant session
    try:
        # Find and delete from database
        async with AsyncSessionLocal() as cleanup_db:
            result = await cleanup_db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            existing_session = result.scalar_one_or_none()

            if existing_session:
                logger.info(f"Found existing character assistant session: {instance_id}")

                # Remove from registry first
                registry = get_session_registry()
                removed = registry.remove_session(instance_id)
                if removed:
                    logger.info(f"Removed character assistant from registry: {instance_id}")
                else:
                    logger.debug(f"Character assistant not in registry (already cleaned up): {instance_id}")

                # Delete from database (cascade will handle messages)
                await cleanup_db.delete(existing_session)
                await cleanup_db.commit()
                logger.info(f"Deleted character assistant from database: {instance_id}")
            else:
                logger.info("No existing character assistant session found")

        # Create fresh character assistant session in background
        from ..core.task_manager import get_task_manager

        async def create_character_assistant():
            """Background task to create character assistant session."""
            try:
                from ..sessions.session_context import SessionContext

                registry = get_session_registry()

                # Create session context
                context = SessionContext(
                    instance_id=instance_id,
                    session_id=None,  # Will be created fresh
                    character_id="character_assistant",
                    specialists=None,
                    project_id=None,
                    project_path=str(settings.agents_dir),
                    model=None
                )

                # Create new session via registry
                logger.info(f"Creating fresh character assistant session: {instance_id}")
                session = await registry.get_or_create_session(
                    context=context,
                    role=SessionRole.CHARACTER_ASSISTANT
                )

                logger.info(f"✓ Character assistant session recreated: {instance_id}")

            except Exception as e:
                logger.error(f"Failed to create character assistant session: {e}", exc_info=True)

        # Schedule background task
        task_manager = get_task_manager()
        task_manager.create_task(
            create_character_assistant(),
            name=f"recreate_character_assistant"
        )

        return {
            "status": "success",
            "message": "Character assistant session recreation initiated",
            "instance_id": instance_id
        }

    except Exception as e:
        logger.error(f"Failed to recreate character assistant: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to recreate character assistant: {str(e)}"
        )
