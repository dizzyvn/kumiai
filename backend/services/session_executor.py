"""
Session Executor Service

Unified session query execution with database persistence.
Executes queries, consumes responses, and broadcasts events to SSE clients.

Uses SessionRegistry to ensure single session instance per instance_id.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from backend.core.constants import (
    MAX_INACTIVITY_SECONDS,
    MAX_TOTAL_DURATION_SECONDS,
)
from backend.core.database import AsyncSessionLocal
from backend.core.task_manager import get_task_manager
from backend.services.message_service import MessageService
from backend.services.sse_manager import sse_manager
from backend.models.database import AgentInstance as DBAgentInstance
from backend.config.session_roles import SessionRole
from backend.sessions import get_session_registry, BaseSession
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Query message types"""
    NORMAL = "normal"  # Regular message, queue normally
    INTERRUPT = "interrupt"  # Cancel current execution, clear queue, execute immediately


@dataclass
class QueryMessage:
    """Envelope for queued messages"""
    message: str
    sender_role: str  # "user", "pm", "orchestrator"
    sender_id: Optional[str] = None  # Character ID of the sender
    sender_name: Optional[str] = None  # Display name of the sender
    sender_instance: Optional[str] = None  # Session instance ID of the sender
    query_type: QueryType = QueryType.NORMAL
    timestamp: float = field(default_factory=time.time)


class SessionExecutor:
    """Unified session query execution with database persistence and queueing"""

    def __init__(self):
        # Message queue infrastructure for batching and concurrency control
        self._queues: dict[str, asyncio.Queue] = {}
        self._locks: dict[str, asyncio.Lock] = {}  # Per-session execution lock
        self._processing: dict[str, bool] = {}  # Track if session is processing
        self._interrupt_events: dict[str, asyncio.Event] = {}  # For cancellation
        logger.info("[SESSION_EXECUTOR] Initialized with queue support")

    async def _broadcast_event(self, instance_id: str, event: Dict[str, Any]) -> None:
        """Broadcast event to SSE clients."""
        await sse_manager.broadcast(instance_id, event)

    async def _check_timeout(
        self,
        instance_id: str,
        start_time: float,
        last_event_time: float,
        event_count: int
    ) -> None:
        """
        Check for timeout conditions and raise RuntimeError if exceeded.

        Args:
            instance_id: Session instance ID
            start_time: Query start time
            last_event_time: Last event timestamp
            event_count: Number of events processed

        Raises:
            RuntimeError: If timeout exceeded
        """
        current_time = asyncio.get_event_loop().time()
        total_elapsed = current_time - start_time
        inactivity = current_time - last_event_time

        # Check absolute maximum duration
        if total_elapsed > MAX_TOTAL_DURATION_SECONDS:
            error_msg = f"Query exceeded maximum duration of {int(MAX_TOTAL_DURATION_SECONDS/60)} minutes"
            logger.error(
                f"[SESSION_EXECUTOR] {error_msg} for {instance_id} "
                f"(total_elapsed={total_elapsed:.1f}s, events={event_count})"
            )
            await self._broadcast_event(instance_id, {
                "type": "error",
                "error": error_msg,
                "instanceId": instance_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            raise RuntimeError(f"{error_msg} for {instance_id}")

        # Check inactivity timeout
        if inactivity > MAX_INACTIVITY_SECONDS:
            error_msg = f"No activity for {int(inactivity/60)} minutes - session appears hung"
            logger.error(
                f"[SESSION_EXECUTOR] {error_msg} for {instance_id} "
                f"(inactivity={inactivity:.1f}s, total_elapsed={total_elapsed:.1f}s, events={event_count})"
            )
            await self._broadcast_event(instance_id, {
                "type": "error",
                "error": error_msg,
                "instanceId": instance_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            raise RuntimeError(f"{error_msg} for {instance_id}")

    async def enqueue(self, instance_id: str, query_msg: QueryMessage) -> None:
        """
        Add message to session's queue and trigger processing.

        This is the main entry point for message submission.
        If the session is currently processing, messages are queued and batched.

        Args:
            instance_id: Target instance ID
            query_msg: Message to enqueue
        """
        # Initialize session queue if needed
        if instance_id not in self._queues:
            self._queues[instance_id] = asyncio.Queue()
            self._locks[instance_id] = asyncio.Lock()
            self._processing[instance_id] = False
            self._interrupt_events[instance_id] = asyncio.Event()
            logger.info(f"[SESSION_EXECUTOR] Created queue for instance {instance_id}")

        # Handle interrupt: clear queue and signal cancellation
        if query_msg.query_type == QueryType.INTERRUPT:
            logger.warning(f"[SESSION_EXECUTOR] INTERRUPT received for instance {instance_id}")

            # Clear existing queue
            cleared_count = 0
            while not self._queues[instance_id].empty():
                try:
                    self._queues[instance_id].get_nowait()
                    cleared_count += 1
                except asyncio.QueueEmpty:
                    break

            if cleared_count > 0:
                logger.info(f"[SESSION_EXECUTOR] Cleared {cleared_count} queued messages for instance {instance_id}")

            # Signal interrupt to cancel current execution
            self._interrupt_events[instance_id].set()

        # Enqueue message
        await self._queues[instance_id].put(query_msg)
        queue_size = self._queues[instance_id].qsize()

        logger.info(
            f"[SESSION_EXECUTOR] Enqueued message from {query_msg.sender_role} "
            f"for instance {instance_id} (queue size: {queue_size}, "
            f"type: {query_msg.query_type.value})"
        )

        # Trigger processing if not already running
        if not self._processing[instance_id]:
            logger.info(f"[SESSION_EXECUTOR] Triggering processing for instance {instance_id}")
            task_manager = get_task_manager()
            task_manager.create_task(
                self._process_queue(instance_id),
                name=f"process_queue_{instance_id}",
            )
        else:
            logger.debug(f"[SESSION_EXECUTOR] Instance {instance_id} already processing, message queued")

    async def _process_queue(self, instance_id: str) -> None:
        """
        Process queued messages for a session.
        Collects ALL queued messages and executes them as a batch.

        Args:
            instance_id: Instance to process
        """
        async with self._locks[instance_id]:
            self._processing[instance_id] = True
            logger.info(f"[SESSION_EXECUTOR] Started queue processing for instance {instance_id}")

            try:
                while not self._queues[instance_id].empty():
                    # Collect ALL queued messages
                    messages = []
                    while not self._queues[instance_id].empty():
                        try:
                            msg = self._queues[instance_id].get_nowait()
                            messages.append(msg)
                        except asyncio.QueueEmpty:
                            break

                    if not messages:
                        logger.debug(f"[SESSION_EXECUTOR] No messages to process for instance {instance_id}")
                        break

                    logger.info(
                        f"[SESSION_EXECUTOR] Collected {len(messages)} messages for batch execution "
                        f"(instance {instance_id})"
                    )

                    # Execute batch
                    try:
                        await self._execute_batch(instance_id, messages)
                    except Exception as e:
                        logger.error(
                            f"[SESSION_EXECUTOR] Error executing batch for instance {instance_id}: {e}",
                            exc_info=True,
                        )
                        # Continue processing remaining messages even if batch fails

            finally:
                self._processing[instance_id] = False
                logger.info(f"[SESSION_EXECUTOR] Stopped queue processing for instance {instance_id}")

    async def _execute_batch(self, instance_id: str, messages: list[QueryMessage]) -> None:
        """
        Execute a batch of messages as single query.

        Args:
            instance_id: Target instance
            messages: List of messages to combine and execute
        """
        logger.info(
            f"[SESSION_EXECUTOR] Executing batch of {len(messages)} messages for instance {instance_id}"
        )

        # Convert to Claude SDK message format
        # Pass each message separately to preserve sender attribution
        # execute_query will persist each individually and combine content for Claude
        messages_list = [{
            "role": "user",
            "content": self._format_message_with_sender(msg),
            "sender_role": msg.sender_role,
            "sender_id": msg.sender_id,
            "sender_name": msg.sender_name,
            "sender_instance": msg.sender_instance,
        } for msg in messages]

        logger.debug(f"[SESSION_EXECUTOR] Prepared {len(messages_list)} messages with sender attribution")

        # Execute using the unified execution method (without queueing)
        await self._execute_query_direct(
            instance_id=instance_id,
            messages=messages_list
        )

    def _format_message_with_sender(self, msg: QueryMessage) -> str:
        """
        Format a single message with sender attribution.

        Args:
            msg: QueryMessage to format

        Returns:
            Formatted message string with sender attribution
        """
        # Use sender_name (display name) for attribution
        sender = msg.sender_name if msg.sender_name else msg.sender_role.upper()

        # Build sender info with role
        if msg.sender_role == "pm":
            sender_info = f"{sender} (PM)"
        elif msg.sender_role == "user":
            sender_info = "User"
        elif msg.sender_role == "orchestrator":
            sender_info = f"{sender} (Orchestrator)"
        elif msg.sender_role == "specialist" or msg.sender_role == "single_specialist":
            sender_info = f"{sender} (Specialist)"
        else:
            sender_info = sender

        # Append sender instance ID if available
        if msg.sender_instance:
            sender_info += f", from: {msg.sender_instance}"

        prefix = f"**Message from {sender_info}:**\n"

        return prefix + msg.message

    def _combine_messages(self, messages: list[QueryMessage]) -> str:
        """
        Combine multiple queued messages into single context-rich query.
        ALWAYS includes sender attribution so agent knows who sent the message.

        DEPRECATED: This method is kept for backward compatibility but is no longer
        used by _execute_batch. Messages are now passed individually to preserve
        sender attribution in the database.

        Args:
            messages: List of messages to combine

        Returns:
            Combined message string with sender attribution
        """
        # Single message - still add sender attribution
        if len(messages) == 1:
            return self._format_message_with_sender(messages[0])

        # Multiple messages - show all with context
        parts = [
            "You have received multiple messages while you were processing. "
            "Here they are in chronological order:\n"
        ]

        for i, msg in enumerate(messages, 1):
            sender = msg.sender_name or msg.sender_role.upper()

            # Add role context for clarity
            if msg.sender_role == "pm":
                sender_label = f"{sender} (PM)"
            elif msg.sender_role == "orchestrator":
                sender_label = f"{sender} (Orchestrator)"
            elif msg.sender_role == "specialist":
                sender_label = f"{sender} (Specialist)"
            else:
                sender_label = sender

            parts.append(f"\n**Message {i} from {sender_label}:**\n{msg.message}\n")

        parts.append("\nPlease address all of these messages in your response.")

        combined = "".join(parts)
        logger.debug(f"[SESSION_EXECUTOR] Combined {len(messages)} messages into single query")

        return combined

    def is_processing(self, instance_id: str) -> bool:
        """
        Check if instance is currently processing.

        Args:
            instance_id: Instance ID to check

        Returns:
            True if instance is processing, False otherwise
        """
        return self._processing.get(instance_id, False)

    def get_queue_size(self, instance_id: str) -> int:
        """
        Get number of queued messages for an instance.

        Args:
            instance_id: Instance ID to check

        Returns:
            Number of queued messages
        """
        if instance_id not in self._queues:
            return 0
        return self._queues[instance_id].qsize()

    def get_interrupt_event(self, instance_id: str) -> Optional[asyncio.Event]:
        """
        Get interrupt event for an instance (for cancellation support).

        Args:
            instance_id: Instance ID

        Returns:
            Interrupt event if instance exists, None otherwise
        """
        return self._interrupt_events.get(instance_id)

    def clear_interrupt(self, instance_id: str) -> None:
        """
        Clear interrupt flag for an instance.

        Args:
            instance_id: Instance ID
        """
        if instance_id in self._interrupt_events:
            self._interrupt_events[instance_id].clear()
            logger.debug(f"[SESSION_EXECUTOR] Cleared interrupt flag for instance {instance_id}")

    def signal_interrupt(self, instance_id: str) -> None:
        """
        Signal interrupt for an instance (used by cancel API).

        Args:
            instance_id: Instance ID to interrupt
        """
        # Initialize if needed
        if instance_id not in self._interrupt_events:
            self._interrupt_events[instance_id] = asyncio.Event()

        self._interrupt_events[instance_id].set()
        logger.info(f"[SESSION_EXECUTOR] Interrupt signal set for instance {instance_id}")

    async def execute_query_unified(
        self, instance_id: str, messages: list[dict], use_stream_manager: bool = True,
        task_name: Optional[str] = None
    ) -> None:
        """
        Execute query using unified SessionStreamManager with automatic queueing.

        This method now supports message queueing - if the session is currently
        processing, messages are queued and batched together.

        Args:
            instance_id: Session instance ID
            messages: List of message dicts with role and content
            use_stream_manager: Whether to use SessionStreamManager (default: True)
            task_name: Unique task name for this query execution (for cancellation tracking)
        """
        # Extract message content and sender attribution
        if len(messages) == 1:
            msg = messages[0]
            content = msg.get("content", "")
            sender_role = msg.get("sender_role", "user")
            sender_name = msg.get("sender_name")

            # Create QueryMessage for queueing
            query_msg = QueryMessage(
                message=content,
                sender_role=sender_role,
                sender_name=sender_name,
                query_type=QueryType.NORMAL
            )

            # Enqueue the message (will trigger processing if not busy)
            await self.enqueue(instance_id, query_msg)
        else:
            # Multiple messages provided - execute directly without queueing
            logger.info(f"[SESSION_EXECUTOR] Executing {len(messages)} messages directly (no queueing)")
            await self._execute_query_direct(instance_id, messages, use_stream_manager, task_name)

    async def _execute_query_direct(
        self, instance_id: str, messages: list[dict], use_stream_manager: bool = True,
        task_name: Optional[str] = None
    ) -> None:
        """
        Direct query execution (bypasses queueing).
        Called by _execute_batch after messages are combined.

        Args:
            instance_id: Session instance ID
            messages: List of message dicts with role and content
            use_stream_manager: Whether to use SessionStreamManager (default: True)
            task_name: Unique task name for this query execution (for cancellation tracking)
        """
        logger.info(f"[SESSION_EXECUTOR] Starting direct query execution for {instance_id} with task_name={task_name}")

        try:
            # Get session from registry (or load from database if not cached)
            session = await self._get_or_load_session(instance_id)

            # Store the current task name for cancellation tracking
            if task_name:
                session._current_task_name = task_name
                logger.info(f"[SESSION_EXECUTOR] Stored task_name={task_name} for {instance_id}")

            # Initialize timeout tracking
            event_count = 0
            start_time = asyncio.get_event_loop().time()
            last_event_time = start_time

            logger.info(
                f"[SESSION_EXECUTOR] Starting timeout monitoring for {instance_id}: "
                f"max_inactivity={MAX_INACTIVITY_SECONDS}s, "
                f"max_total={MAX_TOTAL_DURATION_SECONDS}s"
            )

            # Execute query and broadcast events with timeout
            # Timeout after 15 minutes to prevent infinite hangs when Claude crashes
            try:
                # Use asyncio.wait_for for Python 3.10 compatibility (asyncio.timeout requires 3.11+)
                async def execute_with_events():
                    nonlocal event_count, last_event_time  # Access outer scope variables

                    async for event in session.execute_query(messages):
                        # Check for interrupt signal
                        interrupt_event = self.get_interrupt_event(instance_id)
                        if interrupt_event and interrupt_event.is_set():
                            logger.warning(f"[SESSION_EXECUTOR] Interrupt detected for {instance_id}, cancelling")
                            self.clear_interrupt(instance_id)
                            raise RuntimeError(f"Execution interrupted for {instance_id}")

                        event_count += 1

                        # Check timeout conditions
                        await self._check_timeout(instance_id, start_time, last_event_time, event_count)

                        # Log progress every 10 events
                        if event_count % 10 == 0:
                            current_time = asyncio.get_event_loop().time()
                            logger.debug(
                                f"[SESSION_EXECUTOR] Progress for {instance_id}: "
                                f"events={event_count}, elapsed={current_time - start_time:.1f}s"
                            )

                        # Broadcast event and update last event time
                        await self._broadcast_event(instance_id, event)
                        last_event_time = asyncio.get_event_loop().time()

                    logger.info(f"[SESSION_EXECUTOR] Completed direct execution for {instance_id} ({event_count} events)")

                # Execute with 15-minute timeout
                await asyncio.wait_for(execute_with_events(), timeout=900)

            except asyncio.TimeoutError:
                logger.error(f"[SESSION_EXECUTOR] ⏱️ TIMEOUT after 900s for {instance_id} - Claude process likely hung")
                # Broadcast error event
                error_event = {
                    "type": "error",
                    "instanceId": instance_id,
                    "error": "Execution timed out after 15 minutes. Claude process may have crashed.",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self._broadcast_event(instance_id, error_event)

                # Update session status to error
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(DBAgentInstance)
                        .where(DBAgentInstance.instance_id == instance_id)
                        .values(status="error")
                    )
                    await db.commit()

                raise RuntimeError(f"Session {instance_id} timed out - Claude process hung")

        except Exception as e:
            logger.error(f"[SESSION_EXECUTOR] Error in direct execution: {e}", exc_info=True)
            raise
        finally:
            # Clear the current task name to prevent stale references
            # Use the synchronous _clear_current_task() method which cannot fail
            try:
                session = await self._get_or_load_session(instance_id)
                session._clear_current_task()
                logger.info(f"[SESSION_EXECUTOR] Cleared task name for {instance_id}")
            except Exception as e:
                logger.warning(f"[SESSION_EXECUTOR] Failed to get session for task cleanup: {e}")

            # Always cleanup incomplete streaming messages
            try:
                await self._cleanup_streaming_messages(instance_id)
            except Exception as cleanup_error:
                logger.warning(f"[SESSION_EXECUTOR] Cleanup failed: {cleanup_error}")

    async def _get_or_load_session(self, instance_id: str) -> BaseSession:
        """Get session from registry or load from database."""
        registry = get_session_registry()

        # Try to get existing session from registry
        session = registry.get_session(instance_id)
        if session:
            # Check if client subprocess is still alive
            if not session.is_client_alive():
                logger.warning(
                    f"[SESSION_EXECUTOR] Cached session {instance_id} has dead client, "
                    f"attempting to recreate..."
                )
                # Try to recreate the client (will resume session if session_id exists)
                if await session.recreate_client():
                    logger.info(f"[SESSION_EXECUTOR] Successfully recreated client for {instance_id}")
                    return session
                else:
                    # Failed to recreate, remove from registry and reload from database
                    logger.error(
                        f"[SESSION_EXECUTOR] Failed to recreate client for {instance_id}, "
                        f"removing from registry and reloading"
                    )
                    registry.remove_session(instance_id)
                    # Fall through to reload from database
            else:
                logger.info(f"[SESSION_EXECUTOR] Using cached session: {instance_id}")
                return session

        # Load session metadata from database
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
            )
            instance = result.scalar_one_or_none()

            if not instance:
                raise ValueError(f"Session {instance_id} not found in database")

            # Determine role
            role = SessionRole(instance.role)

            # Reconstruct the correct project_path based on role
            # Single-specialist and orchestrator sessions use .sessions/instance-id subdirectory
            # PM and other sessions use project root directly
            from pathlib import Path
            project_root = Path(instance.project_path)

            if role in (SessionRole.SINGLE_SPECIALIST, SessionRole.ORCHESTRATOR):
                # Reconstruct the full session path
                session_path = str(project_root / ".sessions" / instance_id)
                logger.info(f"[SESSION_EXECUTOR] Reconstructed session path for {role.value}: {session_path}")
            else:
                # Use project root directly
                session_path = instance.project_path
                logger.info(f"[SESSION_EXECUTOR] Using project root for {role.value}: {session_path}")

            # Create session via registry (will initialize it)
            logger.info(f"[SESSION_EXECUTOR] Loading session from database: {instance_id}")
            session = await registry.get_or_create_session(
                instance_id=instance_id,
                role=role,
                project_path=session_path,  # Use the correct reconstructed path
                project_id=instance.project_id,
                character_id=instance.character_id,
                specialists=instance.selected_specialists or [],
            )

            return session

    async def _cleanup_streaming_messages(self, instance_id: str) -> None:
        """
        Clean up any incomplete streaming messages.

        NOTE: With transition-based message recording, there are no more "incomplete"
        messages. Each content block is finalized immediately on transitions.
        This method is kept as a no-op for backward compatibility.

        Args:
            instance_id: Session instance ID
        """
        # No-op: transition-based approach doesn't leave incomplete messages
        logger.debug(f"[SESSION_EXECUTOR] Cleanup called for {instance_id} (no-op with transition-based recording)")


# Global instance
session_executor = SessionExecutor()


# Utility function for new code to use unified execution
async def execute_session_query(instance_id: str, messages: list[dict]) -> None:
    """
    Convenience function for unified session execution.

    Args:
        instance_id: Session instance ID
        messages: List of message dicts with role and content
    """
    await session_executor.execute_query_unified(instance_id, messages)
