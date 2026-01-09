"""Agent management service."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid
from datetime import datetime
from pathlib import Path
import logging

from ..core.database import AsyncSessionLocal
from ..models.database import AgentInstance as DBAgentInstance, Character, DEFAULT_PROJECT_ID
from ..models.schemas import (
    AgentInstance,
    AgentCharacter,
    SpawnAgentRequest,
)
from .claude_client import client_manager

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent instances."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # DEPRECATED: spawn_agent() and check_pm_exists() removed
    # Session creation now unified via SessionFactory (see backend/sessions/)
    # Legacy code removed in session creation unification migration

    async def list_agents(self, project_id: Optional[str] = None) -> list[AgentInstance]:
        """Get all active agent instances, optionally filtered by project_id."""
        query = select(DBAgentInstance)
        if project_id:
            query = query.where(DBAgentInstance.project_id == project_id)

        result = await self.db.execute(query)
        instances = result.scalars().all()

        agent_list = []
        for instance in instances:
            # Load character info from agent.md file if character_id is set
            character_info = None
            if instance.character_id:
                from ..utils.character_file import load_character_from_file
                from ..models.database import Character
                try:
                    character = await load_character_from_file(instance.character_id)
                    if character:
                        # Load capabilities from database (not from file!)
                        skills = []
                        result = await self.db.execute(
                            select(Character).where(Character.id == instance.character_id)
                        )
                        db_char = result.scalar_one_or_none()
                        if db_char:
                            skills = db_char.allowed_skills or []

                        character_info = AgentCharacter(
                            id=instance.character_id,
                            name=character.name,
                            avatar=character.avatar or instance.character_id,
                            description=character.description,
                            color=character.color,
                            skills=skills,
                            default_model=character.default_model,
                            personality=character.personality,
                        )
                except Exception as e:
                    logger.warning(f"Failed to load character {instance.character_id} from agent.md: {e}")

            # Fallback to default Claude if no character loaded
            if not character_info:
                character_info = AgentCharacter(
                    id="claude",
                    name="Claude",
                    avatar="🤖",
                    description="AI assistant with access to specialists",
                    color="#6B7280",
                    skills=[],
                    default_model="sonnet",
                    personality=None,
                )

            agent_list.append(
                AgentInstance(
                    instance_id=instance.instance_id,
                    character=character_info,
                    role=instance.role or "orchestrator",
                    status=instance.status,
                    current_session_description=instance.session_description,
                    project_id=instance.project_id or DEFAULT_PROJECT_ID,
                    project_path=instance.project_path,
                    session_id=instance.session_id,
                    started_at=instance.started_at,
                    output_lines=instance.output_lines,
                    kanban_stage=instance.kanban_stage,
                    selected_specialists=instance.selected_specialists,
                    actual_tools=instance.actual_tools,
                    actual_mcp_servers=instance.actual_mcp_servers,
                    actual_skills=instance.actual_skills,
                )
            )

        return agent_list

    async def get_agent(self, instance_id: str) -> Optional[AgentInstance]:
        """Get a specific agent instance."""
        result = await self.db.execute(
            select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
        )
        instance = result.scalar_one_or_none()

        if not instance:
            return None

        # Load character info from agent.md file if character_id is set
        character_info = None
        if instance.character_id:
            from ..utils.character_file import load_character_from_file
            from ..models.database import Character
            try:
                character = await load_character_from_file(instance.character_id)
                if character:
                    # Load capabilities from database (not from file!)
                    skills = []
                    result = await self.db.execute(
                        select(Character).where(Character.id == instance.character_id)
                    )
                    db_char = result.scalar_one_or_none()
                    if db_char:
                        skills = db_char.allowed_skills or []

                    character_info = AgentCharacter(
                        id=instance.character_id,
                        name=character.name,
                        avatar=character.avatar or instance.character_id,
                        description=character.description,
                        color=character.color,
                        skills=skills,
                        default_model=character.default_model,
                        personality=character.personality,
                    )
            except Exception as e:
                logger.warning(f"Failed to load character {instance.character_id} from agent.md: {e}")

        # Fallback to default Claude if no character loaded
        if not character_info:
            character_info = AgentCharacter(
                id="claude",
                name="Claude",
                avatar="🤖",
                description="AI assistant with access to specialists",
                color="#6B7280",
                skills=[],
                default_model="sonnet",
                personality=None,
            )

        return AgentInstance(
            instance_id=instance.instance_id,
            character=character_info,
            role=instance.role or "orchestrator",
            status=instance.status,
            current_session_description=instance.session_description,
            project_id=instance.project_id or DEFAULT_PROJECT_ID,
            project_path=instance.project_path,
            session_id=instance.session_id,
            started_at=instance.started_at,
            output_lines=instance.output_lines,
            kanban_stage=instance.kanban_stage,
            selected_specialists=instance.selected_specialists,
            actual_tools=instance.actual_tools,
            actual_mcp_servers=instance.actual_mcp_servers,
            actual_skills=instance.actual_skills,
        )

    async def update_agent_stage(self, instance_id: str, stage: str) -> bool:
        """Update agent's kanban stage.

        If moving to 'active' stage and session hasn't been started yet,
        automatically queue the initial task description.
        """
        result = await self.db.execute(
            select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
        )
        instance = result.scalar_one_or_none()

        if not instance:
            return False

        # Check if moving TO "active" stage and session hasn't auto-started yet
        old_stage = instance.kanban_stage
        is_moving_to_active = (stage == "active" and old_stage != "active")
        should_auto_start = is_moving_to_active and not instance.auto_started and instance.role == "orchestrator"

        if should_auto_start:
            logger.info(f"[AGENT_SERVICE] Auto-starting session {instance_id} on stage change to 'active'")
            print(f"[AGENT_SERVICE] Auto-starting session {instance_id} on stage change to 'active'")

            # Queue the initial task description
            from ..services.session_executor import session_executor, QueryMessage

            query_msg = QueryMessage(
                message=instance.session_description,
                sender_role="system",
                sender_name="Stage Change"
            )

            await session_executor.enqueue(instance_id, query_msg)

            # Mark as auto-started
            instance.auto_started = True

        instance.kanban_stage = stage
        await self.db.commit()
        return True

    async def delete_agent(self, instance_id: str) -> bool:
        """Delete an agent instance."""
        result = await self.db.execute(
            select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
        )
        instance = result.scalar_one_or_none()

        if not instance:
            return False

        # Remove Claude client
        await client_manager.remove_client(instance_id)

        # Delete from database
        await self.db.delete(instance)
        await self.db.commit()
        return True

    async def cancel_agent(self, instance_id: str) -> bool:
        """Cancel a running agent."""
        client = await client_manager.get_client(instance_id)
        if not client:
            return False

        # Interrupt the agent
        await client.interrupt()

        # Update status
        result = await self.db.execute(
            select(DBAgentInstance).where(DBAgentInstance.instance_id == instance_id)
        )
        instance = result.scalar_one_or_none()

        if instance:
            instance.status = "cancelled"
            await self.db.commit()

        return True
