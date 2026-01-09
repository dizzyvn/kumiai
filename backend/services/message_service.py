"""Service for managing session messages."""
import uuid
import json
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.sql import func
from ..models.database import SessionMessage as SessionMessageModel
from ..models.schemas import SessionMessage


class MessageService:
    """Service for handling session message operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_message(
        self,
        instance_id: str,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[list[dict]] = None,  # List of tool uses
        tool_use_id: Optional[str] = None,
        is_error: bool = False,
        sender_role: Optional[str] = None,
        sender_id: Optional[str] = None,  # Character ID of the sender
        sender_name: Optional[str] = None,  # Display name of the sender
        sender_instance: Optional[str] = None,  # Session instance ID of the sender
        sequence: int = 0,  # Execution order within a response
        cost_usd: Optional[float] = None,
        content_type: str = "text",  # "text", "tool_use", "transition"
        message_id: Optional[str] = None,
        response_id: Optional[str] = None,  # UUID shared by all blocks in same response
    ) -> SessionMessage:
        """
        Save a new message to the database.

        Args:
            instance_id: The session instance ID
            role: Message role (user, assistant, tool, system, transition)
            content: Message content
            agent_name: Optional agent name for specialist messages
            tool_name: Optional tool name for tool messages
            tool_args: Optional tool arguments for tool messages
            tool_use_id: Optional Claude tool use ID for tool results
            is_error: Whether the tool result is an error
            sender_role: Who sent this message ("user", "pm", "orchestrator")
            sender_id: Character ID of the sender (e.g., "alex")
            sender_name: Display name of sender (e.g., "Alex")
            sender_instance: Session instance ID of the sender (e.g., "pm-0b3ce10b")
            sequence: Execution order within a response (for ordering tools with text)
            cost_usd: Optional cost in USD for this message
            content_type: Type of content ("text", "tool_use", "transition")
            message_id: Optional custom message ID (for idempotency)
            response_id: UUID shared by all blocks in same response

        Returns:
            The created SessionMessage
        """
        msg_id = message_id or str(uuid.uuid4())

        message = SessionMessageModel(
            id=msg_id,
            instance_id=instance_id,
            role=role,
            content=content,
            agent_name=agent_name,
            tool_name=tool_name,
            tool_args=json.dumps(tool_args) if tool_args else None,
            tool_use_id=tool_use_id,
            is_error=is_error,
            sender_role=sender_role,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_instance=sender_instance,
            sequence=sequence,
            cost_usd=cost_usd,
            content_type=content_type,
            response_id=response_id,
            timestamp=datetime.utcnow(),
        )

        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)

        return self._to_schema(message)

    async def get_messages(
        self,
        instance_id: str,
        limit: int = 100,
        before: Optional[datetime] = None,
    ) -> list[SessionMessage]:
        """
        Get message history for a session.

        Args:
            instance_id: The session instance ID
            limit: Maximum number of messages to return (default 100)
            before: Optional timestamp to get messages before (for pagination)

        Returns:
            List of SessionMessage objects ordered by timestamp ascending
        """
        query = select(SessionMessageModel).where(
            SessionMessageModel.instance_id == instance_id
        )

        if before:
            query = query.where(SessionMessageModel.timestamp < before)

        query = query.order_by(SessionMessageModel.timestamp.desc()).limit(limit)

        result = await self.db.execute(query)
        messages = result.scalars().all()

        # Reverse to get chronological order (oldest first)
        return [self._to_schema(msg) for msg in reversed(messages)]

    async def finalize_text_block(
        self,
        instance_id: str,
        content: str,
        sequence: int,
        sender_role: Optional[str] = None,
        sender_id: Optional[str] = None,
        sender_name: Optional[str] = None,
        sender_instance: Optional[str] = None,
        response_id: Optional[str] = None,
    ) -> SessionMessage:
        """
        Finalize a text content block when transitioning to a different content type.

        Args:
            instance_id: The session instance ID
            content: The accumulated text content
            sequence: Execution sequence number
            sender_role: Optional sender role
            sender_id: Optional sender character ID
            sender_name: Optional sender display name
            sender_instance: Optional sender session instance ID
            response_id: UUID shared by all blocks in same response

        Returns:
            The saved SessionMessage
        """
        return await self.save_message(
            instance_id=instance_id,
            role="assistant",
            content=content,
            content_type="text",
            sequence=sequence,
            sender_role=sender_role,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_instance=sender_instance,
            response_id=response_id,
        )

    async def delete_message(self, message_id: str) -> bool:
        """
        Delete a message from the database.

        Used primarily to clean up incomplete/partial messages when a session is interrupted.

        Args:
            message_id: The message ID to delete

        Returns:
            True if message was deleted, False if not found
        """
        result = await self.db.execute(
            select(SessionMessageModel).where(SessionMessageModel.id == message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return False

        await self.db.delete(message)
        await self.db.commit()
        return True

    async def get_message_by_id(self, message_id: str) -> Optional[SessionMessage]:
        """
        Get a specific message by ID.

        Args:
            message_id: The message ID

        Returns:
            The SessionMessage or None if not found
        """
        result = await self.db.execute(
            select(SessionMessageModel).where(SessionMessageModel.id == message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return None

        return self._to_schema(message)

    def _to_schema(self, message: SessionMessageModel) -> SessionMessage:
        """Convert database model to Pydantic schema."""
        tool_args = None
        if message.tool_args:
            try:
                tool_args = json.loads(message.tool_args)
            except json.JSONDecodeError:
                tool_args = []  # Return empty list on parse error (tool_args is a list type)

        return SessionMessage(
            id=message.id,
            instance_id=message.instance_id,
            role=message.role,
            content=message.content,
            agent_name=message.agent_name,
            tool_name=message.tool_name,
            tool_args=tool_args,
            tool_use_id=message.tool_use_id,
            is_error=message.is_error,
            sender_role=message.sender_role,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            sender_instance=message.sender_instance,
            sequence=message.sequence,
            timestamp=message.timestamp,
            cost_usd=message.cost_usd,
            content_type=message.content_type or 'text',
            response_id=message.response_id,
        )
