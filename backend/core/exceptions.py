"""
Standardized exception classes for API error responses.

All API errors should use these exception classes for consistent error handling.
"""

from fastapi import HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any


class ErrorResponse(BaseModel):
    """Standard error response model"""
    error: str
    code: str
    details: Optional[Dict[str, Any]] = None


class AppException(HTTPException):
    """
    Base exception for all application errors.

    Provides consistent error response format across all endpoints.
    """
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status_code,
            detail={"error": message, "code": code, "details": details}
        )


class SessionNotFoundError(AppException):
    """Raised when session instance is not found"""
    def __init__(self, instance_id: str):
        super().__init__(
            message=f"Session {instance_id} not found",
            code="SESSION_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"instance_id": instance_id}
        )


class SessionBusyError(AppException):
    """Raised when session is already processing another request"""
    def __init__(self, instance_id: str):
        super().__init__(
            message=f"Session {instance_id} is busy processing another request",
            code="SESSION_BUSY",
            status_code=status.HTTP_409_CONFLICT,
            details={"instance_id": instance_id}
        )


class InvalidRequestError(AppException):
    """Raised when request validation fails"""
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            code="INVALID_REQUEST",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"field": field} if field else None
        )


class ProjectNotFoundError(AppException):
    """Raised when project is not found"""
    def __init__(self, project_id: str):
        super().__init__(
            message=f"Project {project_id} not found",
            code="PROJECT_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"project_id": project_id}
        )


class CharacterNotFoundError(AppException):
    """Raised when character is not found"""
    def __init__(self, character_id: str):
        super().__init__(
            message=f"Character {character_id} not found",
            code="CHARACTER_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"character_id": character_id}
        )


class SkillNotFoundError(AppException):
    """Raised when skill is not found"""
    def __init__(self, skill_id: str):
        super().__init__(
            message=f"Skill {skill_id} not found",
            code="SKILL_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"skill_id": skill_id}
        )


class SessionInitializationError(AppException):
    """Raised when session initialization fails"""
    def __init__(self, message: str, instance_id: Optional[str] = None):
        super().__init__(
            message=f"Session initialization failed: {message}",
            code="SESSION_INIT_FAILED",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"instance_id": instance_id} if instance_id else None
        )


class SessionTimeoutError(AppException):
    """Raised when session operation times out"""
    def __init__(self, message: str, instance_id: str):
        super().__init__(
            message=message,
            code="SESSION_TIMEOUT",
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            details={"instance_id": instance_id}
        )
