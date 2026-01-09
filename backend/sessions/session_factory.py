"""
Session factory for creating appropriate session types.

Centralizes session creation logic and routing based on configuration.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from backend.config.session_roles import SessionRole
from backend.sessions.session_context import SessionContext
from backend.sessions.base_session import BaseSession
from backend.sessions.specialist_session import SpecialistSession
from backend.sessions.orchestrator_session import OrchestratorSession
from backend.sessions.pm_session import PMSession
from backend.sessions.assistant_session import AssistantSession

logger = logging.getLogger(__name__)


class SessionFactory:
    """
    Factory for creating session instances.

    Handles intelligent routing based on parameters:
    - PM role → PMSession
    - Multiple specialists → OrchestratorSession
    - Single specialist/character → SpecialistSession
    - Assistant roles → AssistantSession
    """

    @staticmethod
    async def create_session(
        instance_id: str,
        role: SessionRole,
        project_path: str,
        character_id: Optional[str] = None,
        specialists: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        **kwargs
    ) -> BaseSession:
        """
        Create appropriate session type based on configuration.

        Args:
            instance_id: Unique instance identifier
            role: Session role enum
            project_path: Path to project/session directory
            character_id: Optional character ID for specialist sessions
            specialists: Optional list of specialist IDs for orchestrator
            project_id: Optional project ID for PM sessions
            **kwargs: Additional context (model, metadata, etc.)

        Returns:
            Initialized session instance (not yet connected to Claude)

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate inputs
        SessionFactory._validate_configuration(
            role=role,
            character_id=character_id,
            specialists=specialists,
            project_id=project_id
        )

        # Build context
        context = SessionContext(
            character_id=character_id,
            specialists=specialists or [],
            project_id=project_id,
            project_path=Path(project_path),
            working_directory=Path(project_path),
            instance_id=instance_id,
            session_id=kwargs.get("existing_claude_session_id"),  # Resume existing session if available
            model=kwargs.get("model", "sonnet"),
            metadata=kwargs
        )

        # Select session class based on configuration
        session_class = SessionFactory._select_session_class(
            role=role,
            has_character=bool(character_id),
            specialist_count=len(specialists) if specialists else 0
        )

        logger.info(f"[FACTORY] Creating {session_class.__name__} for instance {instance_id}")
        logger.info(f"[FACTORY]   - Role: {role.value}")
        logger.info(f"[FACTORY]   - Character: {character_id or 'None'}")
        logger.info(f"[FACTORY]   - Specialists: {len(specialists) if specialists else 0}")

        # Create session instance
        session = session_class(
            instance_id=instance_id,
            role=role,
            project_path=Path(project_path),
            context=context
        )

        return session

    @staticmethod
    def _select_session_class(
        role: SessionRole,
        has_character: bool,
        specialist_count: int
    ) -> type:
        """
        Determine which session class to use based on configuration.

        Args:
            role: Session role enum
            has_character: Whether character_id is specified
            specialist_count: Number of specialists

        Returns:
            Session class to instantiate
        """
        # PM sessions
        if role == SessionRole.PM:
            return PMSession

        # Assistant sessions
        if role in (SessionRole.CHARACTER_ASSISTANT, SessionRole.SKILL_ASSISTANT):
            return AssistantSession

        # Orchestrator vs Specialist
        if specialist_count > 1:
            # Multiple specialists → Orchestrator
            return OrchestratorSession
        elif specialist_count == 1 or has_character:
            # Single specialist or direct character → Specialist
            return SpecialistSession
        else:
            # Fallback to specialist (plain Claude)
            logger.warning("[FACTORY] No character or specialists specified, using SpecialistSession as fallback")
            return SpecialistSession

    @staticmethod
    def _validate_configuration(
        role: SessionRole,
        character_id: Optional[str],
        specialists: Optional[List[str]],
        project_id: Optional[str]
    ):
        """
        Validate session configuration before creation.

        Args:
            role: Session role enum
            character_id: Optional character ID
            specialists: Optional specialist list
            project_id: Optional project ID

        Raises:
            ValueError: If configuration is invalid
        """
        # PM sessions should have project_id
        if role == SessionRole.PM and not project_id:
            logger.warning("[FACTORY] PM session created without project_id")

        # SINGLE_SPECIALIST role requires character_id
        if role == SessionRole.SINGLE_SPECIALIST and not character_id and not specialists:
            raise ValueError(
                "SINGLE_SPECIALIST role requires either character_id or specialists"
            )

        # ORCHESTRATOR role should have specialists (but we can handle single specialist)
        if role == SessionRole.ORCHESTRATOR and not specialists:
            logger.warning("[FACTORY] ORCHESTRATOR role without specialists (will use character_id if available)")

        # Can't have both character_id and multiple specialists
        if character_id and specialists and len(specialists) > 1:
            raise ValueError(
                "Cannot specify both character_id and multiple specialists. "
                "Use either character_id for single specialist or specialists list for orchestrator."
            )

        # Validate specialist list
        if specialists:
            if not isinstance(specialists, list):
                raise ValueError(f"specialists must be a list, got {type(specialists)}")

            if any(not isinstance(s, str) or not s.strip() for s in specialists):
                raise ValueError("All specialists must be non-empty strings")

    @staticmethod
    def create_pm_session(
        instance_id: str,
        project_path: str,
        project_id: str,
        character_id: Optional[str] = None,
        **kwargs
    ) -> PMSession:
        """
        Convenience method to create PM session.

        Args:
            instance_id: Unique instance ID
            project_path: Project directory path
            project_id: Project ID
            character_id: Optional PM persona character
            **kwargs: Additional context

        Returns:
            PMSession instance
        """
        context = SessionContext(
            character_id=character_id,
            project_id=project_id,
            project_path=Path(project_path),
            instance_id=instance_id,
            model=kwargs.get("model", "sonnet"),
            metadata=kwargs
        )

        return PMSession(
            instance_id=instance_id,
            role=SessionRole.PM,
            project_path=Path(project_path),
            context=context
        )

    @staticmethod
    def create_specialist_session(
        instance_id: str,
        project_path: str,
        character_id: str,
        project_id: Optional[str] = None,
        **kwargs
    ) -> SpecialistSession:
        """
        Convenience method to create specialist session.

        Args:
            instance_id: Unique instance ID
            project_path: Project directory path
            character_id: Character ID
            project_id: Optional project ID
            **kwargs: Additional context

        Returns:
            SpecialistSession instance
        """
        context = SessionContext(
            character_id=character_id,
            project_id=project_id,
            project_path=Path(project_path),
            instance_id=instance_id,
            model=kwargs.get("model", "sonnet"),
            metadata=kwargs
        )

        return SpecialistSession(
            instance_id=instance_id,
            role=SessionRole.SINGLE_SPECIALIST,
            project_path=Path(project_path),
            context=context
        )

    @staticmethod
    def create_orchestrator_session(
        instance_id: str,
        project_path: str,
        specialists: List[str],
        project_id: Optional[str] = None,
        **kwargs
    ) -> OrchestratorSession:
        """
        Convenience method to create orchestrator session.

        Args:
            instance_id: Unique instance ID
            project_path: Project directory path
            specialists: List of specialist character IDs
            project_id: Optional project ID
            **kwargs: Additional context

        Returns:
            OrchestratorSession instance
        """
        if not specialists or len(specialists) < 2:
            raise ValueError("OrchestratorSession requires at least 2 specialists")

        context = SessionContext(
            specialists=specialists,
            project_id=project_id,
            project_path=Path(project_path),
            instance_id=instance_id,
            model=kwargs.get("model", "sonnet"),
            metadata=kwargs
        )

        return OrchestratorSession(
            instance_id=instance_id,
            role=SessionRole.ORCHESTRATOR,
            project_path=Path(project_path),
            context=context
        )
