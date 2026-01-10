"""
Session registry for managing active session instances.

Ensures singleton pattern - only one session object per instance_id.
"""

import asyncio
import logging
import time
from typing import Dict, Optional
from pathlib import Path

from backend.sessions.base_session import BaseSession
from backend.sessions.session_factory import SessionFactory
from backend.config.session_roles import SessionRole

logger = logging.getLogger(__name__)


class SessionRegistry:
    """
    Singleton registry for active session instances.

    Ensures only one session object exists per instance_id to prevent
    duplicate Claude clients and inconsistent tool configurations.
    """

    _instance: Optional["SessionRegistry"] = None

    def __init__(self):
        """Initialize empty registry."""
        self._sessions: Dict[str, BaseSession] = {}
        self._locks: Dict[str, asyncio.Lock] = {}  # Per-instance locks for creation
        self._global_lock = asyncio.Lock()  # Lock for managing the locks dict
        self._last_activity: Dict[str, float] = {}  # Track last activity time per session
        self._cleanup_task: Optional[asyncio.Task] = None  # Background cleanup task
        self._total_cleaned = 0  # Stats: total sessions cleaned up
        self._session_timeout = 3600  # 1 hour of inactivity before cleanup

    @classmethod
    def get_instance(cls) -> "SessionRegistry":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = SessionRegistry()
            # Start background cleanup task
            cls._instance._start_cleanup_loop()
            logger.info("[REGISTRY] Initialized SessionRegistry singleton with cleanup loop")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (useful for testing)."""
        cls._instance = None

    async def get_or_create_session(
        self,
        instance_id: str,
        role: SessionRole,
        project_path: str,
        character_id: Optional[str] = None,
        specialists: Optional[list[str]] = None,
        project_id: Optional[str] = None,
        **kwargs
    ) -> BaseSession:
        """
        Get existing session or create new one.

        Args:
            instance_id: Unique instance identifier
            role: Session role enum
            project_path: Path to project/session directory
            character_id: Optional character ID
            specialists: Optional specialist list
            project_id: Optional project ID
            **kwargs: Additional context

        Returns:
            Session instance (existing or newly created)
        """
        start_time = time.time()

        # Return existing session if already registered (fast path, no lock needed)
        if instance_id in self._sessions:
            logger.info(f"[REGISTRY] Reusing existing session: {instance_id}")
            return self._sessions[instance_id]

        # Get or create a lock for this specific instance_id
        async with self._global_lock:
            if instance_id not in self._locks:
                self._locks[instance_id] = asyncio.Lock()
            instance_lock = self._locks[instance_id]

        # Check database BEFORE acquiring lock to reduce critical section
        from backend.core.database import AsyncSessionLocal
        from backend.models.database import AgentInstance
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        db_start = time.time()
        existing_claude_session_id = None
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(AgentInstance).where(AgentInstance.instance_id == instance_id)
                )
                existing_record = result.scalar_one_or_none()
                if existing_record and existing_record.session_id:
                    existing_claude_session_id = existing_record.session_id
                    logger.info(f"[REGISTRY] Found existing Claude session_id: {existing_claude_session_id}")
            except Exception as e:
                logger.error(f"[REGISTRY] Error querying database: {e}")
        db_duration = time.time() - db_start
        logger.info(f"[REGISTRY] Database lookup completed in {db_duration:.3f}s")

        # Pass existing session_id to factory via kwargs
        if existing_claude_session_id:
            kwargs['existing_claude_session_id'] = existing_claude_session_id

        # Acquire instance-specific lock to prevent race conditions
        async with instance_lock:
            # Double-check pattern: another coroutine might have created it while we waited
            if instance_id in self._sessions:
                logger.info(f"[REGISTRY] Session created by another request: {instance_id}")
                return self._sessions[instance_id]

            # Create new session via factory
            logger.info(f"[REGISTRY] Creating new session: {instance_id}")
            try:
                session = await SessionFactory.create_session(
                    instance_id=instance_id,
                    role=role,
                    project_path=project_path,
                    character_id=character_id,
                    specialists=specialists,
                    project_id=project_id,
                    **kwargs
                )

                # Initialize the session (creates Claude client, stores in DB)
                await session.initialize()

                # Register the session
                self._sessions[instance_id] = session
                self._last_activity[instance_id] = time.time()  # Track activity
                total_duration = time.time() - start_time
                logger.info(f"[REGISTRY] ✓ Registered session: {instance_id} (total: {total_duration:.2f}s)")

                return session

            except IntegrityError as e:
                # Race condition: another process/thread created this session in DB
                logger.warning(f"[REGISTRY] Database IntegrityError for {instance_id}, attempting to load existing session")
                # Try one more time to get it from DB and create session object
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(AgentInstance).where(AgentInstance.instance_id == instance_id)
                    )
                    existing_record = result.scalar_one_or_none()
                    if existing_record and existing_record.session_id:
                        kwargs['existing_claude_session_id'] = existing_record.session_id

                # Create session object (won't try to insert into DB since it exists)
                session = await SessionFactory.create_session(
                    instance_id=instance_id,
                    role=role,
                    project_path=project_path,
                    character_id=character_id,
                    specialists=specialists,
                    project_id=project_id,
                    **kwargs
                )
                await session.initialize()
                self._sessions[instance_id] = session
                self._last_activity[instance_id] = time.time()  # Track activity
                return session
            finally:
                # Clean up the lock after creation is complete
                async with self._global_lock:
                    if instance_id in self._locks:
                        del self._locks[instance_id]

    def get_session(self, instance_id: str) -> Optional[BaseSession]:
        """
        Get existing session without creating.

        Args:
            instance_id: Instance identifier

        Returns:
            Session instance or None if not found
        """
        session = self._sessions.get(instance_id)
        if session:
            # Update last activity time when session is accessed
            self._last_activity[instance_id] = time.time()
        return session

    def remove_session(self, instance_id: str) -> bool:
        """
        Remove session from registry.

        Args:
            instance_id: Instance identifier

        Returns:
            True if session was removed, False if not found
        """
        if instance_id in self._sessions:
            del self._sessions[instance_id]
            # Also remove from activity tracking
            self._last_activity.pop(instance_id, None)
            logger.info(f"[REGISTRY] Removed session: {instance_id}")
            return True
        return False

    def list_sessions(self) -> list[str]:
        """
        List all registered session IDs.

        Returns:
            List of instance IDs
        """
        return list(self._sessions.keys())

    def session_count(self) -> int:
        """Get count of registered sessions."""
        return len(self._sessions)

    def _start_cleanup_loop(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("[REGISTRY] Started session cleanup loop")

    async def _cleanup_loop(self):
        """
        Background task that periodically cleans up stale sessions.
        Runs every 5 minutes and removes sessions idle for > 1 hour.
        """
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self._cleanup_stale_sessions()
            except asyncio.CancelledError:
                logger.info("[REGISTRY] Cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"[REGISTRY] Error in cleanup loop: {e}", exc_info=True)
                # Continue running despite errors

    async def _cleanup_stale_sessions(self):
        """Clean up sessions that have been idle for too long or have dead clients."""
        now = time.time()
        stale_sessions = []
        dead_client_sessions = []

        # Find stale sessions and dead client sessions
        for instance_id, last_time in self._last_activity.items():
            session = self._sessions.get(instance_id)
            if not session:
                continue

            # Check for dead client subprocess
            if not session.is_client_alive():
                logger.warning(
                    f"[REGISTRY] Session {instance_id} has dead client subprocess"
                )
                dead_client_sessions.append(instance_id)
            # Check for idle timeout
            elif now - last_time > self._session_timeout:
                stale_sessions.append(instance_id)

        # Clean up dead client sessions first (higher priority)
        if dead_client_sessions:
            logger.warning(
                f"[REGISTRY] Found {len(dead_client_sessions)} sessions with dead clients to clean up"
            )
            for instance_id in dead_client_sessions:
                try:
                    await self._cleanup_session(instance_id)
                    self._total_cleaned += 1
                except Exception as e:
                    logger.error(
                        f"[REGISTRY] Error cleaning up dead client session {instance_id}: {e}",
                        exc_info=True,
                    )

        # Clean up idle sessions
        if stale_sessions:
            logger.info(
                f"[REGISTRY] Found {len(stale_sessions)} stale sessions to clean up "
                f"(idle > {self._session_timeout}s)"
            )
            for instance_id in stale_sessions:
                try:
                    await self._cleanup_session(instance_id)
                    self._total_cleaned += 1
                except Exception as e:
                    logger.error(
                        f"[REGISTRY] Error cleaning up session {instance_id}: {e}",
                        exc_info=True,
                    )

    async def _cleanup_session(self, instance_id: str):
        """
        Properly cleanup a session by cancelling it and removing from registry.

        Args:
            instance_id: Instance identifier to clean up
        """
        session = self._sessions.get(instance_id)
        if not session:
            return

        logger.info(f"[REGISTRY] Cleaning up stale session: {instance_id}")

        try:
            # Cancel the session (stops Claude client)
            await session.cancel()
        except Exception as e:
            logger.error(f"[REGISTRY] Error cancelling session {instance_id}: {e}")

        # Remove from registry
        self.remove_session(instance_id)

    def get_cleanup_stats(self) -> dict:
        """
        Get statistics about session cleanup.

        Returns:
            Dictionary with cleanup statistics
        """
        return {
            "active_sessions": len(self._sessions),
            "total_cleaned": self._total_cleaned,
            "session_timeout_seconds": self._session_timeout,
            "oldest_session_age_seconds": (
                max(
                    (time.time() - last_time for last_time in self._last_activity.values()),
                    default=0,
                )
                if self._last_activity
                else 0
            ),
        }

    async def shutdown(self):
        """
        Gracefully shutdown the registry.
        Cancels cleanup loop and all active sessions.
        """
        logger.info("[REGISTRY] Shutting down session registry...")

        # Cancel cleanup loop
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Cancel all active sessions
        session_ids = list(self._sessions.keys())
        for instance_id in session_ids:
            try:
                await self._cleanup_session(instance_id)
            except Exception as e:
                logger.error(f"[REGISTRY] Error during shutdown cleanup of {instance_id}: {e}")

        logger.info("[REGISTRY] Shutdown complete")


# Global instance getter for convenience
def get_session_registry() -> SessionRegistry:
    """Get the global session registry instance."""
    return SessionRegistry.get_instance()
