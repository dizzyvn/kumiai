"""
Base session class with common functionality.

All session types inherit from this abstract base class.
"""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    SystemMessage,
    AssistantMessage,
    ResultMessage,
)

from backend.config.session_roles import SessionRole
from backend.core.constants import CONNECTION_TIMEOUT_SECONDS
from backend.core.database import AsyncSessionLocal
from backend.models.database import AgentInstance, SessionMessage
from backend.services.sse_manager import sse_manager
from backend.sessions.session_context import SessionContext
from backend.utils.database_retry import with_db_retry

logger = logging.getLogger(__name__)


class BaseSession(ABC):
    """
    Abstract base class for all session types.

    Provides common functionality:
    - Database persistence
    - Event broadcasting
    - Message handling
    - Status updates

    Subclasses must implement:
    - _create_claude_options(): Build ClaudeAgentOptions for this session type
    """

    def __init__(
        self,
        instance_id: str,
        role: SessionRole,
        project_path: Path,
        context: SessionContext,
    ):
        """
        Initialize base session.

        Args:
            instance_id: Unique instance identifier
            role: Session role (PM, ORCHESTRATOR, SINGLE_SPECIALIST, etc.)
            project_path: Path to project/session directory
            context: Session configuration context
        """
        self.instance_id = instance_id
        self.role = role
        self.project_path = project_path
        self.context = context

        # Claude SDK client
        self.client: Optional[ClaudeSDKClient] = None
        self.session_id: Optional[str] = None

        # Character metadata (loaded from agent.md if applicable)
        self.character_id: Optional[str] = None  # Character ID (e.g., "alex")
        self.character_name: Optional[str] = None  # Display name (e.g., "Alex")
        self.character_avatar: Optional[str] = None
        self.character_color: Optional[str] = None

        # Track current active task name for cancellation
        self._current_task_name: Optional[str] = None

    @abstractmethod
    async def _create_claude_options(self) -> ClaudeAgentOptions:
        """
        Create Claude SDK options for this session type.

        Each session type implements its own configuration logic:
        - PM: PM management tools
        - Specialist: Character tools + MCP servers
        - Orchestrator: Multi-agent with specialists
        - Assistant: File editing tools

        Returns:
            Configured ClaudeAgentOptions
        """
        pass

    async def initialize(self) -> str:
        """
        Initialize Claude client and session.

        Returns:
            Session ID for Claude SDK

        Raises:
            ValueError: If initialization fails
        """
        start_time = time.time()
        logger.info(f"[SESSION] Initializing {self.role.value} session: {self.instance_id}")

        # Check if we're resuming an existing session
        existing_session_id = self.context.session_id
        if existing_session_id:
            logger.info(f"[SESSION] Attempting to resume existing Claude session")
            logger.info(f"[SESSION]   session_id: {existing_session_id}")
            logger.info(f"[SESSION]   working_dir: {self.project_path}")
            self.session_id = existing_session_id
            # Register session mapping when resuming
            from ..services.claude_client import client_manager
            client_manager.set_session(self.instance_id, existing_session_id)
            logger.info(f"[SESSION] Registered resumed session mapping: {self.instance_id} → {existing_session_id}")
        else:
            logger.info(f"[SESSION] Creating new Claude session")
            logger.info(f"[SESSION]   working_dir: {self.project_path}")

        # Create Claude options (subclass-specific)
        options_start = time.time()
        logger.info(f"[SESSION] Creating Claude options...")
        options = await self._create_claude_options()
        options_duration = time.time() - options_start
        logger.info(f"[SESSION] ✓ Claude options created in {options_duration:.2f}s")

        # Extract and store tools/MCP servers for database tracking
        self._configured_tools = options.allowed_tools or []
        self._configured_mcp_servers = list(options.mcp_servers.keys()) if options.mcp_servers else []

        logger.info(f"[SESSION] Configured {len(self._configured_tools)} tools, {len(self._configured_mcp_servers)} MCP servers")

        # Create Claude SDK client
        # Note: Session resumption is handled via ClaudeAgentOptions(resume=...) in _create_claude_options()
        client_start = time.time()
        self.client = ClaudeSDKClient(options=options)
        client_duration = time.time() - client_start
        logger.info(f"[SESSION] ✓ Claude SDK client created in {client_duration:.2f}s")

        # Connect the client with timeout protection
        connect_start = time.time()
        logger.info(f"[SESSION] Connecting to Claude SDK...")
        try:
            await asyncio.wait_for(
                self.client.connect(),
                timeout=CONNECTION_TIMEOUT_SECONDS
            )
            connect_duration = time.time() - connect_start
            logger.info(f"[SESSION] ✓ Claude SDK connected in {connect_duration:.2f}s")
        except asyncio.TimeoutError:
            logger.error(f"[SESSION] Connection timeout after 30 seconds for {self.instance_id}")
            raise RuntimeError(f"Session initialization timeout after 30s for {self.instance_id}")
        except Exception as e:
            error_message = str(e)
            logger.error(f"[SESSION] Connection failed with error: {error_message}")
            logger.error(f"[SESSION] Error type: {type(e).__name__}")

            # Check if this is a resume failure (conversation not found)
            # ProcessError from Claude SDK often has "No conversation found" in earlier logs
            is_resume_failure = (
                existing_session_id and (
                    "No conversation found" in error_message or
                    "conversation not found" in error_message.lower() or
                    (type(e).__name__ == "ProcessError" and "exit code 1" in error_message)
                )
            )

            if is_resume_failure:
                logger.warning(f"[SESSION] Resume failed during connect - conversation not found for session_id: {existing_session_id}")
                logger.warning(f"[SESSION] Claude Code conversation may have been deleted. Clearing session_id and retrying with fresh session...")

                # Clear the stale session_id from database
                await self._clear_session_id()

                # Recreate client without resume session
                logger.info(f"[SESSION] Creating fresh Claude SDK client without resume...")
                # Create fresh options without resume_session by calling _create_claude_options again
                # This ensures we use the correct parameters for each session type
                self.session_id = None  # Clear before recreating options
                fresh_options = await self._create_claude_options()

                self.client = ClaudeSDKClient(options=fresh_options)

                # Retry connection without resume with timeout
                retry_start = time.time()
                await asyncio.wait_for(
                    self.client.connect(),
                    timeout=CONNECTION_TIMEOUT_SECONDS
                )
                connect_duration = time.time() - retry_start
                logger.info(f"[SESSION] ✓ Claude SDK connected with fresh session in {connect_duration:.2f}s")
            else:
                # Re-raise other errors
                raise

        # Note: session_id will be captured from the first message stream (init message)
        # It's not available on the client object itself
        # If resuming, we already set self.session_id = existing_session_id above
        if existing_session_id:
            logger.info(f"[SESSION] ✓ Client connected with resume session_id: {existing_session_id}")
        else:
            logger.info(f"[SESSION] ✓ Client connected - session_id will be captured from first query")

        # Store session in database (session_id may be updated after first query)
        store_start = time.time()
        await self._store_session()
        store_duration = time.time() - store_start
        logger.info(f"[SESSION] ✓ Session stored in database in {store_duration:.2f}s")

        total_duration = time.time() - start_time
        logger.info(f"[SESSION] ✓ Initialized {self.role.value} session in {total_duration:.2f}s")
        logger.info(f"[SESSION]   instance_id: {self.instance_id}")
        logger.info(f"[SESSION]   claude_session_id: {self.session_id or 'pending'}")
        logger.info(f"[SESSION]   Breakdown: options={options_duration:.2f}s, client={client_duration:.2f}s, connect={connect_duration:.2f}s, store={store_duration:.2f}s")

        return self.instance_id  # Return instance_id, not session_id

    async def _finalize_tool_block(
        self,
        tool_use: dict,
        message_service: Any,
        response_id: Optional[str] = None,
        interrupted: bool = False,
    ) -> None:
        """
        Helper method to finalize and save a tool use block.

        Args:
            tool_use: Dict containing tool metadata (name, id, input, sequence)
            message_service: MessageService instance for database operations
            response_id: UUID shared by all blocks in same response
            interrupted: Whether this tool was interrupted (adds notice to content)
        """
        tool_name = tool_use.get("name", "unknown_tool")
        tool_args = tool_use.get("input", {})
        tool_id = tool_use.get("id", "")
        tool_sequence = tool_use.get("sequence", 0)
        msg_id = f"tool_call_{self.instance_id}_{tool_id}" if tool_id else None

        content = f"Tool: {tool_name}"
        if interrupted:
            content += " *[interrupted]*"

        await message_service.save_message(
            instance_id=self.instance_id,
            role="tool_call",
            content=content,
            tool_name=tool_name,
            tool_args=[{"name": tool_name, "id": tool_id, "input": tool_args}],
            content_type="tool_use",
            sequence=tool_sequence,
            message_id=msg_id,
            response_id=response_id,
        )
        logger.info(f"[SESSION] Finalized tool block: {tool_name} (sequence={tool_sequence}, interrupted={interrupted})")

    async def execute_query(
        self,
        messages: List[Dict[str, Any]]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute query and stream responses.

        Args:
            messages: List of message dicts with role/content

        Yields:
            Event dicts for SSE streaming
        """
        import traceback
        logger.debug(f"[SESSION] ====== EXECUTE_QUERY CALLED ======")
        logger.debug(f"[SESSION] Instance ID: {self.instance_id}")
        logger.debug(f"[SESSION] Call stack:")
        for line in traceback.format_stack()[:-1]:
            logger.debug(f"  {line.strip()}")
        logger.debug(f"[SESSION] ==========================================")

        if not self.client:
            raise RuntimeError("Session not initialized. Call initialize() first.")

        # Clear any stale interrupt signals from previous queries
        # This prevents race condition where new query sees old interrupt signal
        from backend.services.session_executor import session_executor
        interrupt_event = session_executor.get_interrupt_event(self.instance_id)
        if interrupt_event and interrupt_event.is_set():
            logger.debug(f"[🔍 DEBUG] STALE INTERRUPT DETECTED! Clearing it before starting new query for {self.instance_id}")
            session_executor.clear_interrupt(self.instance_id)
            logger.debug(f"[🔍 DEBUG] Stale interrupt cleared, continuing with query execution")
        else:
            logger.debug(f"[🔍 DEBUG] No stale interrupt, starting clean query for {self.instance_id}")

        # Persist user messages
        logger.debug(f"[🔍 DEBUG] Persisting user messages...")
        await self._persist_user_messages(messages)
        logger.debug(f"[🔍 DEBUG] User messages persisted successfully")

        # Update status to working
        await self._update_status("working")

        # Broadcast status change event
        working_event = {
            "type": "status_change",
            "status": "working",
            "instanceId": self.instance_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._broadcast_event(working_event)
        yield working_event

        # Combine messages into single query string
        query_text = "\n".join(msg.get("content", "") for msg in messages if msg.get("role") == "user")

        # Execute query via Claude SDK
        try:
            # Send query to Claude
            logger.debug(f"[🔍 DEBUG] Sending query to Claude SDK: {query_text[:100]}...")
            await self.client.query(query_text)
            logger.debug(f"[🔍 DEBUG] Query sent successfully, starting to receive messages")

            # Generate response_id for grouping all messages from this response
            response_id = str(uuid.uuid4())
            logger.debug(f"[SESSION] Generated response_id for this query response: {response_id}")

            # Track content blocks and transitions
            response_text = ""  # Accumulated text for current text block
            current_content_type = None  # None, 'text', or 'tool_use'

            # Track current tool
            current_tool_use = None  # Current tool being accumulated
            current_tool_input_json = ""

            # Track sequence for ordering messages in execution order
            sequence_counter = 0

            # Buffer for batched delta broadcasting (performance optimization)
            batched_deltas = []

            # Determine sender attribution based on role and character
            sender_role = None
            sender_id = None  # Character ID of the sender
            sender_name = None  # Display name of the sender
            sender_instance = self.instance_id  # Session instance ID
            if self.role.value == "pm":
                sender_role = "pm"
                sender_id = self.character_id
                sender_name = self.character_name  # Should be set in pm_session
            elif self.role.value == "orchestrator":
                sender_role = "orchestrator"
                sender_id = self.character_id
                sender_name = self.character_name  # May be None for orchestrator
            elif self.character_id:
                sender_role = "specialist"
                sender_id = self.character_id
                sender_name = self.character_name  # Should be set in specialist_session

            logger.debug(f"[🔍 DEBUG] Starting message receive loop...")
            message_count = 0

            async for message in self.client.receive_messages():
                message_count += 1
                logger.debug(f"[🔍 DEBUG] Received message #{message_count}: {type(message).__name__}")

                # Check for interrupt signal BEFORE processing each message
                from backend.services.session_executor import session_executor
                interrupt_event = session_executor.get_interrupt_event(self.instance_id)
                if interrupt_event and interrupt_event.is_set():
                    logger.warning(f"[🔍 DEBUG] INTERRUPT DETECTED! Calling client.interrupt()")
                    # Clear interrupt flag for next execution
                    session_executor.clear_interrupt(self.instance_id)
                    # Interrupt Claude SDK - this will cleanly stop the current query
                    await self.client.interrupt()
                    logger.debug(f"[🔍 DEBUG] client.interrupt() called, raising CancelledError")

                    # Raise CancelledError to trigger cleanup
                    # The client will be reused for the next query (SDK handles state cleanup)
                    raise asyncio.CancelledError("Session interrupted by user")

                # Capture session_id from init message (first message in stream)
                if hasattr(message, 'subtype') and message.subtype == 'init':
                    if not self.session_id:  # Only capture if we don't have one yet
                        session_data = getattr(message, 'data', {})
                        if isinstance(session_data, dict):
                            captured_session_id = session_data.get('session_id')
                            if captured_session_id:
                                logger.info(f"[SESSION] Captured session_id from init message: {captured_session_id}")
                                self.session_id = captured_session_id
                                # Update database with captured session_id
                                await self._update_session_id(captured_session_id)
                                # Register session mapping for remind tool and other features
                                from ..services.claude_client import client_manager
                                client_manager.set_session(self.instance_id, captured_session_id)
                                logger.info(f"[SESSION] Registered session mapping: {self.instance_id} → {captured_session_id}")

                # Check if this is ResultMessage - it signals the stream is complete
                if isinstance(message, ResultMessage):
                    # Flush any remaining batched deltas before breaking
                    if batched_deltas:
                        combined_content = "".join(batched_deltas)
                        combined_delta = {
                            "type": "stream_delta",
                            "role": self.role.value,
                            "instanceId": self.instance_id,
                            "content": combined_content,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        # NOTE: Don't broadcast here - session_executor will broadcast
                        yield combined_delta
                        batched_deltas.clear()
                    break

                # Convert Claude SDK message to SSE event format (returns list of events)
                events = await self._convert_message_to_event(message)

                # Track response content and tool uses from StreamEvent deltas
                if hasattr(message, 'event') and isinstance(message.event, dict):
                    event = message.event
                    msg_type = event.get("type")

                    if msg_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            response_text += delta.get("text", "")
                        elif delta.get("type") == "input_json_delta":
                            # Accumulate tool input JSON
                            partial = delta.get("partial_json", "")
                            current_tool_input_json += partial
                            logger.debug(f"[SESSION] Accumulating tool input: {len(current_tool_input_json)} chars total")

                    elif msg_type == "content_block_start":
                        content_block = event.get("content_block", {})
                        block_type = content_block.get("type")  # "text" or "tool_use"

                        # Detect content type transition
                        new_content_type = "tool_use" if block_type == "tool_use" else "text"

                        # Check if we need to finalize the current block
                        # Case 1: Content type changed (text→tool or tool→text)
                        # Case 2: Both are tool_use but it's a NEW tool (tool→tool)
                        should_finalize = False

                        if current_content_type and current_content_type != new_content_type:
                            # Content type transition
                            should_finalize = True
                        elif current_content_type == "tool_use" and new_content_type == "tool_use" and current_tool_use:
                            # Tool→Tool transition: finalize previous tool
                            should_finalize = True
                            logger.info(f"[TRANSITION] Detected tool→tool, finalizing previous tool: {current_tool_use['name']}")

                        if should_finalize:
                            # TRANSITION DETECTED! Finalize the current block
                            logger.info(f"[TRANSITION] Detected {current_content_type} → {new_content_type}")

                            # Clear batched deltas - they'll be saved to DB and loaded by frontend
                            # No need to stream them since we reload from DB on tool_complete
                            if batched_deltas:
                                logger.info(f"[TRANSITION] Clearing {len(batched_deltas)} buffered deltas (will be saved to DB)")
                                batched_deltas.clear()

                            from ..services.message_service import MessageService
                            async with AsyncSessionLocal() as db:
                                message_service = MessageService(db)

                                if current_content_type == "text" and response_text:
                                    # Finalize accumulated text block
                                    logger.info(f"[TRANSITION] Finalizing text block ({len(response_text)} chars, sequence={sequence_counter})")
                                    await message_service.finalize_text_block(
                                        instance_id=self.instance_id,
                                        content=response_text,
                                        sequence=sequence_counter,
                                        sender_role=sender_role,
                                        sender_id=sender_id,
                                        sender_name=sender_name,
                                        sender_instance=sender_instance,
                                        response_id=response_id,
                                    )
                                    sequence_counter += 1  # Increment for next block
                                    response_text = ""  # Reset for next text block

                                elif current_content_type == "tool_use" and current_tool_use:
                                    # Finalize previous tool using helper method
                                    logger.info(f"[TRANSITION] Finalizing tool: {current_tool_use['name']} (sequence={current_tool_use['sequence']})")
                                    await self._finalize_tool_block(current_tool_use, message_service, response_id)
                                    sequence_counter += 1  # Increment for next block
                                    current_tool_use = None
                                    current_tool_input_json = ""

                        # Update current content type
                        current_content_type = new_content_type

                        # Handle new block based on type
                        if block_type == "tool_use":
                            # Start tracking new tool with current sequence
                            tool_name = content_block.get("name")
                            current_tool_use = {
                                "name": tool_name,
                                "id": content_block.get("id"),
                                "input": {},
                                "sequence": sequence_counter  # Assign current counter value
                            }
                            current_tool_input_json = ""
                            logger.debug(f"[SESSION] Tool use started: {tool_name} (sequence: {sequence_counter})")
                        elif block_type == "text":
                            # Text block started (or continuing)
                            logger.debug(f"[SESSION] Text block started/continuing (sequence: {sequence_counter})")

                    elif msg_type == "content_block_stop":
                        # Parse accumulated tool input JSON
                        if current_tool_use and current_tool_input_json:
                            try:
                                import json
                                parsed_input = json.loads(current_tool_input_json)
                                current_tool_use["input"] = parsed_input
                                logger.info(f"[SESSION] ✅ Parsed tool input for {current_tool_use['name']}: {len(str(parsed_input))} chars")

                                # Emit tool_complete event with parsed arguments for real-time UI updates
                                tool_complete_event = {
                                    "type": "tool_complete",
                                    "role": self.role.value,
                                    "instanceId": self.instance_id,
                                    "toolName": current_tool_use["name"],
                                    "toolArgs": parsed_input,
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                                logger.info(f"[SESSION] 🔔 Emitting tool_complete event for {current_tool_use['name']} with args: {list(parsed_input.keys())}")
                                # NOTE: Don't broadcast here - session_executor will broadcast
                                yield tool_complete_event

                            except json.JSONDecodeError as e:
                                logger.error(f"[SESSION] Failed to parse tool input JSON: {e}")
                                logger.error(f"[SESSION] Raw JSON: {current_tool_input_json[:200]}...")
                                current_tool_use["input"] = {}
                        elif current_tool_use:
                            logger.warning(f"[SESSION] Tool {current_tool_use['name']} completed but no input received")

                        # NOTE: Don't save tool here - will be saved on next transition or at end

                # Check if we need to flush batched deltas for real-time streaming
                # NOTE: Removed AssistantMessage flush here because it was clearing batched_deltas
                # BEFORE transition detection could use them. Transitions now handle all flushing.
                # AssistantMessage boundaries are not reliable flush points for text→tool transitions.

                # Process events (deltas are batched, control events yielded immediately)
                for event in events:
                    event_type = event.get("type")

                    if event_type == "stream_delta":
                        # Buffer deltas for batched broadcast
                        delta_content = event.get("content", "")
                        batched_deltas.append(delta_content)
                    else:
                        # Yield control events immediately (tool_use, etc.)
                        # NOTE: Don't broadcast here - session_executor will broadcast
                        yield event
            # Stream loop completed - finalize any remaining blocks
            logger.info(f"[SESSION] Stream loop completed, finalizing remaining blocks")

            from ..services.message_service import MessageService
            async with AsyncSessionLocal() as db:
                message_service = MessageService(db)

                # Finalize remaining text block (if any)
                if current_content_type == "text" and response_text:
                    logger.info(f"[SESSION] Finalizing final text block ({len(response_text)} chars, sequence={sequence_counter})")
                    await message_service.finalize_text_block(
                        instance_id=self.instance_id,
                        content=response_text,
                        sequence=sequence_counter,
                        sender_role=sender_role,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        sender_instance=sender_instance,
                        response_id=response_id,
                    )

                # Finalize remaining tool (if any) - use separate if for defensive coding
                if current_content_type == "tool_use" and current_tool_use:
                    logger.info(f"[SESSION] Finalizing final tool: {current_tool_use['name']}")
                    await self._finalize_tool_block(current_tool_use, message_service, response_id)

            # Send message_complete event
            logger.info(f"[SESSION] Sending message_complete event")
            complete_event = {
                "type": "message_complete",
                "role": self.role.value,
                "instanceId": self.instance_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self._broadcast_event(complete_event)
            yield complete_event

            # Send result event
            logger.info(f"[SESSION] Sending result event")
            result_event = {
                "type": "result",
                "role": self.role.value,
                "status": "completed",
                "instanceId": self.instance_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self._broadcast_event(result_event)
            yield result_event

        except asyncio.CancelledError:
            # Handle cancellation/interruption from cancel() method
            logger.warning(f"[🔍 DEBUG] CancelledError caught for {self.instance_id}")
            logger.warning(f"[🔍 DEBUG] This happens when query is interrupted OR when task is cancelled")

            # Clear any buffered deltas to prevent corruption on next query
            if 'batched_deltas' in locals():
                batched_deltas.clear()

            # Preserve partial blocks with interruption notice
            try:
                from ..services.message_service import MessageService
                async with AsyncSessionLocal() as db:
                    message_service = MessageService(db)

                    # Finalize partial text block with interruption notice
                    if 'current_content_type' in locals() and current_content_type == "text" and 'response_text' in locals() and response_text:
                        interrupted_text = response_text + "\n\n*[Response interrupted by user]*"
                        await message_service.finalize_text_block(
                            instance_id=self.instance_id,
                            content=interrupted_text,
                            sequence=sequence_counter if 'sequence_counter' in locals() else 0,
                            sender_role=sender_role if 'sender_role' in locals() else None,
                            sender_id=sender_id if 'sender_id' in locals() else None,
                            sender_name=sender_name if 'sender_name' in locals() else None,
                            sender_instance=sender_instance if 'sender_instance' in locals() else None,
                            response_id=response_id if 'response_id' in locals() else None,
                        )
                        logger.info(f"[SESSION] Preserved partial text block with interruption notice ({len(response_text)} chars)")

                    # Finalize partial tool (if any) - use separate if for defensive coding
                    if 'current_content_type' in locals() and current_content_type == "tool_use" and 'current_tool_use' in locals() and current_tool_use:
                        logger.info(f"[SESSION] Preserving partial tool with interruption notice: {current_tool_use['name']}")
                        await self._finalize_tool_block(
                            current_tool_use,
                            message_service,
                            response_id if 'response_id' in locals() else None,
                            interrupted=True
                        )

            except Exception as preserve_error:
                logger.error(f"[SESSION] Failed to preserve partial blocks: {preserve_error}")

            # Yield cancelled event (will be rebroadcast by execute_query_unified)
            # Frontend will convert streaming message to permanent message (already saved in DB)
            cancelled_event = {
                "type": "cancelled",
                "instanceId": self.instance_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            # Don't broadcast here - yielding will cause execute_query_unified to broadcast
            # This prevents duplicate cancelled events
            yield cancelled_event

            # Update status to idle after cancellation (ready for next query)
            await self._update_status("idle")

            # Recreate client after interrupt to clear error_during_execution state
            # The interrupted client enters a broken state and causes subsequent queries to fail
            logger.info(f"[SESSION] Recreating client after interruption to clear error state")
            old_session_id = self.session_id  # Preserve session ID

            # Create new options and client
            options = await self._create_claude_options()
            self.client = ClaudeSDKClient(options=options)

            # Reconnect the client
            await self.client.connect()

            # Restore session ID for continuity
            self.session_id = old_session_id
            logger.info(f"[SESSION] Client recreated successfully, ready for next query")

            # Re-raise to properly exit the generator
            raise

        except Exception as e:
            error_message = str(e)
            error_type = type(e).__name__
            logger.error(f"[SESSION] Error during query execution: {error_message} (type: {error_type})")

            # Clear any buffered deltas to prevent corruption
            if 'batched_deltas' in locals():
                batched_deltas.clear()

            # NOTE: With transition-based approach, partial blocks are already saved
            # No need to delete anything - the conversation shows what was completed before error
            logger.info(f"[SESSION] Error occurred - partial blocks already saved via transitions")

            # Check if this is a terminated process error (subprocess crashed)
            is_process_terminated = (
                error_type == "CLIConnectionError" and
                ("terminated process" in error_message.lower() or "exit code" in error_message.lower())
            )

            if is_process_terminated:
                logger.error(
                    f"[SESSION] Claude SDK subprocess has died for {self.instance_id}. "
                    f"Invalidating session from registry to force recreation on next query."
                )
                # Remove session from registry so next query will recreate the client
                from backend.sessions import get_session_registry
                registry = get_session_registry()
                registry.remove_session(self.instance_id)

                error_message = (
                    f"Claude SDK subprocess crashed unexpectedly. "
                    f"The session will be recreated automatically when you send your next message. "
                    f"Please try your request again."
                )

            # Check if this is a resume failure (conversation not found)
            elif "No conversation found" in error_message and self.session_id:
                logger.warning(f"[SESSION] Resume failed - conversation not found for session_id: {self.session_id}")
                logger.warning(f"[SESSION] Claude Code conversation may have been deleted or is in a different directory")
                logger.warning(f"[SESSION] Clearing stale session_id from database...")

                # Clear the stale session_id
                await self._clear_session_id()

                error_message = (
                    f"Resume failed: Claude Code conversation '{self.session_id}' not found. "
                    f"The conversation may have been deleted or cleared. "
                    f"The session has been reset - please send your message again to start a fresh conversation."
                )

            error_event = {
                "type": "error",
                "instanceId": self.instance_id,
                "error": error_message,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self._broadcast_event(error_event)
            yield error_event

            # Update status to idle after error
            await self._update_status("idle")
            idle_event = {
                "type": "status_change",
                "status": "idle",
                "instanceId": self.instance_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self._broadcast_event(idle_event)
            yield idle_event
            raise

        # Update status to idle after successful completion
        logger.info(f"[SESSION] Updating status to idle and sending status_change event")
        await self._update_status("idle")
        idle_event = {
            "type": "status_change",
            "status": "idle",
            "instanceId": self.instance_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._broadcast_event(idle_event)
        yield idle_event
        logger.info(f"[SESSION] Execute query completed successfully")

    def is_client_alive(self) -> bool:
        """
        Check if the Claude SDK client subprocess is still alive.

        Returns:
            True if client exists and subprocess is running, False otherwise
        """
        if not self.client:
            logger.debug(f"[SESSION] is_client_alive: No client for {self.instance_id}")
            return False

        try:
            # Access the underlying transport to check process status
            # The ClaudeSDKClient wraps a transport object
            if hasattr(self.client, '_transport'):
                transport = self.client._transport
                # Check if transport has a process attribute (SubprocessCLITransport)
                if hasattr(transport, '_process') and transport._process:
                    # poll() returns None if process is still running
                    # Returns exit code if process has terminated
                    exit_code = transport._process.poll()
                    if exit_code is not None:
                        logger.warning(
                            f"[SESSION] Client subprocess is dead for {self.instance_id} "
                            f"(exit code: {exit_code})"
                        )
                        return False
                    logger.debug(f"[SESSION] is_client_alive: Process alive for {self.instance_id}")
                    return True

            # If we can't access the process, assume it's alive
            # (better to fail later with proper error than assume dead)
            logger.debug(f"[SESSION] Cannot check process health for {self.instance_id}, assuming alive")
            return True

        except Exception as e:
            logger.warning(f"[SESSION] Error checking client health for {self.instance_id}: {e}")
            # Assume alive on error to avoid false positives
            return True

    async def recreate_client(self) -> bool:
        """
        Recreate the Claude SDK client after a crash.
        Attempts to resume existing session if session_id is available.

        Returns:
            True if client was successfully recreated, False otherwise
        """
        logger.info(f"[SESSION] Recreating client for {self.instance_id} (session_id: {self.session_id})")

        try:
            # Close existing client if it exists
            if self.client:
                try:
                    # Don't await cleanup, just mark it for garbage collection
                    self.client = None
                    logger.debug(f"[SESSION] Released old client reference for {self.instance_id}")
                except Exception as e:
                    logger.warning(f"[SESSION] Error releasing old client: {e}")

            # Create new client with existing session_id if available
            existing_session_id = self.session_id
            logger.info(f"[SESSION] Creating Claude options for recreation (will resume: {existing_session_id is not None})...")
            options = await self._create_claude_options()

            # Create and connect new client
            from backend.services.claude_client import ClaudeSDKClient
            logger.info(f"[SESSION] Creating new ClaudeSDKClient instance...")
            self.client = ClaudeSDKClient(options=options)

            logger.info(f"[SESSION] Connecting recreated client for {self.instance_id} (timeout: {CONNECTION_TIMEOUT_SECONDS}s)...")
            try:
                await asyncio.wait_for(
                    self.client.connect(),
                    timeout=CONNECTION_TIMEOUT_SECONDS
                )
                logger.info(f"[SESSION] ✓ Connection successful for recreated client")
            except asyncio.TimeoutError:
                logger.error(f"[SESSION] ✗ Connection timeout after {CONNECTION_TIMEOUT_SECONDS}s for recreated client")
                raise
            except Exception as conn_error:
                logger.error(f"[SESSION] ✗ Connection failed for recreated client: {conn_error}")
                raise

            if existing_session_id:
                logger.info(
                    f"[SESSION] ✓ Client recreated with session resumption for {self.instance_id} "
                    f"(session_id: {existing_session_id})"
                )
            else:
                logger.info(f"[SESSION] ✓ Client recreated with fresh session for {self.instance_id}")

            return True

        except Exception as e:
            logger.error(
                f"[SESSION] Failed to recreate client for {self.instance_id}: {e}",
                exc_info=True
            )
            return False

    async def cancel(self):
        """Cancel ongoing session execution."""
        logger.info(f"[SESSION] Cancelling session: {self.instance_id}")

        # CRITICAL: Snapshot the task name FIRST before any async operations
        # If we read it later, Query 2 might have changed it already!
        task_to_cancel = self._current_task_name
        logger.info(f"[SESSION] Task to cancel (snapshot): {task_to_cancel}")

        # 1. Interrupt the Claude SDK client immediately (tells API to stop generating)
        if self.client:
            try:
                await self.client.interrupt()
                logger.info(f"[SESSION] Interrupted Claude SDK client: {self.instance_id}")
            except Exception as e:
                logger.warning(f"[SESSION] Error interrupting Claude SDK: {e}")

        # 2. Cancel any active execution tasks via TaskManager
        # This raises CancelledError in the running tasks
        from backend.core.task_manager import get_task_manager
        task_manager = get_task_manager()

        # Cancel the specific task from our snapshot
        # This prevents cancelling Query 2 if it started while we were cancelling Query 1
        unified_count = 0
        if task_to_cancel:
            logger.info(f"[SESSION] Cancelling specific task: {task_to_cancel}")
            unified_count = task_manager.cancel_task_by_name(task_to_cancel)
            # Only clear _current_task_name if it's still the one we cancelled
            # (Query 2 might have already changed it)
            if self._current_task_name == task_to_cancel:
                self._current_task_name = None
                logger.info(f"[SESSION] Cleared task name after cancellation")
            else:
                logger.warning(
                    f"[SESSION] NOT clearing task name: current={self._current_task_name} != cancelled={task_to_cancel} "
                    f"(Query 2 already started)"
                )
        else:
            # Fallback: Cancel all tasks with this instance_id pattern (legacy behavior)
            logger.warning(f"[SESSION] No current task name stored, using fallback cancellation")
            unified_count = task_manager.cancel_task_by_name(f"execute_query_unified_{self.instance_id}")

        # Cancel queue processing tasks (legacy path)
        queue_count = task_manager.cancel_task_by_name(f"process_queue_{self.instance_id}")

        total_cancelled = unified_count + queue_count
        if total_cancelled > 0:
            logger.info(f"[SESSION] Cancelled {total_cancelled} execution task(s) for {self.instance_id} "
                       f"(unified: {unified_count}, queue: {queue_count})")

        # 3. Clear any interrupt signal AFTER cancellation to prevent stale signals
        # This ensures the next query starts clean without detecting a stale interrupt
        from backend.services.session_executor import session_executor
        session_executor.clear_interrupt(self.instance_id)
        logger.info(f"[SESSION] Cleared interrupt signal after cancellation for {self.instance_id}")

        # 4. Give tasks a brief moment to process cancellation
        await asyncio.sleep(0.1)

        # 5. Update status to idle (ready for next query)
        await self._update_status("idle")

        # 6. Broadcast status_change event to ensure UI updates
        # Note: cancelled event is broadcast by CancelledError handler in execute_query()
        # Don't duplicate it here to avoid multiple cancelled events
        await self._broadcast_event({
            "type": "status_change",
            "status": "idle",
            "instanceId": self.instance_id,
            "timestamp": datetime.utcnow().isoformat()
        })

    @with_db_retry(operation_name="store session", max_retries=3, initial_delay=0.1)
    async def _store_session(self):
        """Store or update session instance in database."""
        # CRITICAL: Do ALL path computation OUTSIDE the database transaction
        # Determine project root path before opening database connection
        if self.project_path.parent.name == ".sessions":
            db_project_path = str(self.project_path.parent.parent)
        else:
            db_project_path = str(self.project_path)

        # FAST database transaction - only SELECT + UPDATE/INSERT + COMMIT
        try:
            async with asyncio.timeout(5.0):  # Shorter timeout for minimal transaction
                async with AsyncSessionLocal() as db:
                    try:
                        from sqlalchemy import select

                        # Quick SELECT to check if exists
                        result = await db.execute(
                            select(AgentInstance).where(
                                AgentInstance.instance_id == self.instance_id
                            )
                        )
                        existing = result.scalar_one_or_none()

                        if existing:
                            # Update existing session
                            existing.session_id = self.session_id
                            existing.status = "idle"
                            existing.role = self.role.value
                            existing.actual_tools = self._configured_tools
                            existing.actual_mcp_servers = self._configured_mcp_servers
                        else:
                            # Create new session record (path already computed)
                            session_record = AgentInstance(
                                instance_id=self.instance_id,
                                session_id=self.session_id,
                                character_id=self.context.character_id,
                                project_id=self.context.project_id,
                                project_path=db_project_path,
                                role=self.role.value,
                                status="idle",
                                selected_specialists=self.context.specialists or [],
                                actual_tools=self._configured_tools,
                                actual_mcp_servers=self._configured_mcp_servers,
                            )
                            db.add(session_record)

                        # Commit immediately
                        await db.commit()
                        logger.info(f"[SESSION] ✓ Stored session in database (minimal lock time)")

                    except Exception as e:
                        logger.error(f"[SESSION] Failed to store session: {e}")
                        await db.rollback()
                        raise

        except asyncio.TimeoutError:
            logger.error(
                f"[SESSION] ⏱️ TIMEOUT storing session for {self.instance_id} after 5s - "
                f"database may be locked"
            )
            raise RuntimeError(
                f"Database timeout while storing session {self.instance_id}. "
                f"This may indicate concurrent write contention."
            )

    @with_db_retry(operation_name="persist user messages", max_retries=3, initial_delay=0.1)
    async def _persist_user_messages(self, messages: List[Dict[str, Any]]):
        """Persist user messages to database with sender attribution."""
        # CRITICAL: Do ALL parsing/preparation OUTSIDE the database transaction
        # to minimize lock time and reduce contention

        # Step 1: Parse and prepare message records (NO DATABASE CONNECTION YET)
        message_records = []
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")

                # Get sender attribution from message dict (passed from session_executor)
                sender_role = msg.get("sender_role")
                sender_name = msg.get("sender_name")
                sender_id = msg.get("sender_id")

                logger.debug(f"[SESSION] Processing user message")
                logger.debug(f"[SESSION]   - sender_role: {sender_role}, sender_name: {sender_name}")

                # Always remove sender prefix from content if present
                if content.startswith("**Message from "):
                    import re
                    match = re.match(r'\*\*Message from ([^(:\n]+?)(?:\s*\(([^)]+)\))?\s*:\*\*\s*\n(.*)', content, re.DOTALL)
                    if match:
                        content = match.group(3)

                        # Extract sender metadata from content if not in dict
                        if not sender_role:
                            sender_name = match.group(1).strip()
                            role_text = match.group(2)

                            if role_text:
                                role_lower = role_text.lower()
                                if "project manager" in role_lower or "pm" in role_lower:
                                    sender_role = "pm"
                                elif "orchestrator" in role_lower:
                                    sender_role = "orchestrator"
                                else:
                                    sender_role = "user"
                            else:
                                if sender_name and sender_name.upper() in ["USER", "USER"]:
                                    sender_role = "user"
                                elif sender_name and "Manager" in sender_name:
                                    sender_role = "pm"
                                else:
                                    sender_role = "user"

                # Default to "user" if still no sender info
                if not sender_role:
                    sender_role = "user"

                # Create message record object (not yet persisted)
                message_record = SessionMessage(
                    instance_id=self.instance_id,
                    role="user",
                    content=content,
                    sender_role=sender_role,
                    sender_name=sender_name,
                    sender_id=sender_id,
                    timestamp=datetime.utcnow()
                )
                message_records.append(message_record)

        # Step 2: FAST database transaction - only INSERT + COMMIT
        # This minimizes lock time to the absolute minimum
        try:
            async with asyncio.timeout(5.0):  # Shorter timeout since transaction is now minimal
                async with AsyncSessionLocal() as db:
                    try:
                        # Bulk add all prepared records
                        db.add_all(message_records)

                        # Commit immediately - transaction is very short now
                        await db.commit()

                        logger.info(f"[SESSION] ✓ Persisted {len(message_records)} user message(s) (minimal lock time)")

                    except Exception as e:
                        logger.error(f"[SESSION] Failed to persist user messages: {e}")
                        await db.rollback()
                        raise

        except asyncio.TimeoutError:
            logger.error(
                f"[SESSION] ⏱️ TIMEOUT persisting user messages for {self.instance_id} after 5s - "
                f"database may be locked"
            )
            raise RuntimeError(
                f"Database timeout while persisting messages. "
                f"This may indicate concurrent write contention."
            )

    async def _persist_response(self, content: str, tool_uses: List[Dict[str, Any]]):
        """Persist assistant response to database."""
        async with AsyncSessionLocal() as db:
            try:
                # NOTE: Tool markers are already embedded inline in content
                # during streaming (see content_block_start handling in execute_query)
                # No need to prepend them here

                # Determine sender attribution based on role and character
                sender_role = None
                sender_name = None

                if self.role.value == "pm":
                    sender_role = "pm"
                    sender_name = self.character_name or "Project Manager"
                elif self.role.value == "orchestrator":
                    sender_role = "orchestrator"
                    sender_name = self.character_name or "Orchestrator"
                elif self.character_name:
                    # Specialist or character assistant
                    sender_role = "specialist"
                    sender_name = self.character_name

                # Serialize tool uses to JSON for storage
                import json
                tool_args_json = json.dumps(tool_uses) if tool_uses else None

                message_record = SessionMessage(
                    instance_id=self.instance_id,
                    role="assistant",
                    content=content,
                    sender_role=sender_role,
                    sender_name=sender_name,
                    tool_args=tool_args_json,
                    timestamp=datetime.utcnow()
                )
                db.add(message_record)

                await db.commit()

            except Exception as e:
                logger.error(f"[SESSION] Failed to persist response: {e}")
                await db.rollback()

    async def _update_status(self, status: str):
        """Update session status in database and auto-sync kanban stage."""
        # Pre-compute kanban stage logic OUTSIDE transaction
        # This needs old_status, so we still need to SELECT, but we minimize the logic inside
        new_stage = None
        if self.role.value in ['orchestrator', 'specialist', 'single_specialist', 'character_assistant', 'skill_assistant']:
            # Simple status-to-stage mapping (will be refined inside transaction based on old_status)
            if status in ['working', 'thinking']:
                new_stage = 'active'
            elif status in ['error', 'cancelled']:
                new_stage = 'waiting'
            # idle status handled inside transaction (needs old_status check)

        # FAST database transaction
        try:
            async with asyncio.timeout(3.0):  # Shorter timeout for this simple update
                async with AsyncSessionLocal() as db:
                    try:
                        from sqlalchemy import select

                        # Quick SELECT + UPDATE pattern
                        result = await db.execute(
                            select(AgentInstance).where(
                                AgentInstance.instance_id == self.instance_id
                            )
                        )
                        session_record = result.scalar_one_or_none()

                        if session_record:
                            old_status = session_record.status
                            session_record.status = status

                            # Refine kanban stage for idle status transition
                            if status == 'idle' and self.role.value in ['orchestrator', 'specialist', 'single_specialist', 'character_assistant', 'skill_assistant']:
                                if old_status in ['working', 'thinking']:
                                    new_stage = 'waiting'
                                # else: keep new_stage as None (no change)

                            if new_stage:
                                session_record.kanban_stage = new_stage

                            # Commit immediately
                            await db.commit()

                    except Exception as e:
                        logger.error(f"[SESSION] Failed to update status: {e}")
                        await db.rollback()
                        raise

        except asyncio.TimeoutError:
            logger.warning(
                f"[SESSION] ⏱️ TIMEOUT updating status for {self.instance_id} after 3s - "
                f"database may be locked, continuing anyway"
            )
            # Don't raise - status updates are not critical

    async def _update_session_id(self, session_id: str):
        """Update Claude SDK session_id in database."""
        # OPTIMIZED: Use direct UPDATE statement instead of SELECT + UPDATE
        # This is faster and holds the lock for less time
        try:
            async with asyncio.timeout(3.0):  # Shorter timeout for simple update
                async with AsyncSessionLocal() as db:
                    try:
                        from sqlalchemy import update

                        # Direct UPDATE - no SELECT needed
                        await db.execute(
                            update(AgentInstance)
                            .where(AgentInstance.instance_id == self.instance_id)
                            .values(session_id=session_id)
                        )
                        await db.commit()

                        logger.info(f"[SESSION] ✓ Updated session_id (direct UPDATE)")

                    except Exception as e:
                        logger.error(f"[SESSION] Failed to update session_id: {e}")
                        await db.rollback()
                        raise

        except asyncio.TimeoutError:
            logger.warning(
                f"[SESSION] ⏱️ TIMEOUT updating session_id for {self.instance_id} after 3s - "
                f"database may be locked, continuing anyway"
            )
            # Don't raise - session_id updates are not critical for immediate execution

    async def _clear_session_id(self):
        """Clear stale session_id from database (used when resume fails)."""
        async with AsyncSessionLocal() as db:
            try:
                from sqlalchemy import select
                result = await db.execute(
                    select(AgentInstance).where(
                        AgentInstance.instance_id == self.instance_id
                    )
                )
                session_record = result.scalar_one_or_none()

                if session_record:
                    old_session_id = session_record.session_id
                    session_record.session_id = None
                    await db.commit()
                    logger.info(f"[SESSION] Cleared stale session_id from database: {old_session_id}")

                    # Clear in-memory session_id as well
                    self.session_id = None

            except Exception as e:
                logger.error(f"[SESSION] Failed to clear session_id: {e}")
                await db.rollback()

    async def _broadcast_event(self, event: Dict[str, Any]):
        """Broadcast event via SSE manager."""
        await sse_manager.broadcast(self.instance_id, event)

    async def _convert_message_to_event(self, message: Any) -> List[Dict[str, Any]]:
        """
        Convert Claude SDK message to SSE event format.

        Args:
            message: Claude SDK message object (StreamEvent, SystemMessage, AssistantMessage, or ResultMessage)

        Returns:
            List of event dicts for SSE streaming
        """
        events = []
        msg_class = type(message).__name__

        # Handle StreamEvent objects (streaming events with detailed type info)
        if hasattr(message, 'event') and isinstance(message.event, dict):
            event = message.event
            msg_type = event.get("type")

            if msg_type == "content_block_start":
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    # Tool use started
                    events.append({
                        "type": "tool_use",
                        "role": self.role.value,
                        "instanceId": self.instance_id,
                        "toolName": content_block.get("name"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "metadata": {
                            "tool_use_id": content_block.get("id"),
                            "args": content_block.get("input", {}),
                        },
                    })

            elif msg_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    # Text streaming delta
                    events.append({
                        "type": "stream_delta",
                        "role": self.role.value,
                        "instanceId": self.instance_id,
                        "content": delta.get("text", ""),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                elif delta.get("type") == "input_json_delta":
                    # Tool input delta (partial JSON)
                    events.append({
                        "type": "tool_input_delta",
                        "role": self.role.value,
                        "instanceId": self.instance_id,
                        "content": delta.get("partial_json", ""),
                        "timestamp": datetime.utcnow().isoformat(),
                    })

            elif msg_type == "message_stop":
                # Message completed - handled separately after loop
                pass

        # Handle SystemMessage (init, etc.)
        elif isinstance(message, SystemMessage):
            # System messages are handled internally, no events needed
            pass

        # Handle AssistantMessage (content block boundary marker)
        elif isinstance(message, AssistantMessage):
            # AssistantMessage marks end of a content block
            # No events needed - we handle completion separately
            pass

        # Handle ResultMessage (final message indicating stream completion)
        elif isinstance(message, ResultMessage):
            # ResultMessage indicates the stream has ended
            # No events needed - we handle completion separately
            pass

        return events
