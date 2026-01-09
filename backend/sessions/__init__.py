"""
Session management classes.

This package provides a clean, class-based architecture for managing
different types of Claude Code sessions.
"""

from backend.sessions.session_context import SessionContext
from backend.sessions.base_session import BaseSession
from backend.sessions.specialist_session import SpecialistSession
from backend.sessions.orchestrator_session import OrchestratorSession
from backend.sessions.pm_session import PMSession
from backend.sessions.assistant_session import AssistantSession
from backend.sessions.session_factory import SessionFactory
from backend.sessions.session_registry import SessionRegistry, get_session_registry

__all__ = [
    "SessionContext",
    "BaseSession",
    "SpecialistSession",
    "OrchestratorSession",
    "PMSession",
    "AssistantSession",
    "SessionFactory",
    "SessionRegistry",
    "get_session_registry",
]
