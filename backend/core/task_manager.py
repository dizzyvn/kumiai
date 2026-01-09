"""Background task management with exception handling and cleanup."""
import asyncio
import logging
from typing import Set, Callable, Coroutine, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Manages background asyncio tasks with proper exception handling and cleanup.
    Prevents unhandled exceptions from crashing the event loop.
    """

    def __init__(self):
        self._tasks: Set[asyncio.Task] = set()
        self._task_count = 0
        self._failed_count = 0
        self._completed_count = 0

    def create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        name: str | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> asyncio.Task:
        """
        Create and track a background task with automatic exception handling.

        Args:
            coro: The coroutine to execute
            name: Optional name for the task (for debugging)
            on_error: Optional callback for handling errors

        Returns:
            The created asyncio.Task
        """
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        self._task_count += 1

        # Add cleanup callback
        task.add_done_callback(lambda t: self._on_task_done(t, on_error))

        logger.debug(
            f"[TASK_MANAGER] Created task {name or task.get_name()} "
            f"(total active: {len(self._tasks)})"
        )

        return task

    def _on_task_done(
        self, task: asyncio.Task, on_error: Callable[[Exception], None] | None
    ):
        """
        Callback executed when a task completes.
        Handles exceptions and cleanup.
        """
        # Remove from active tasks
        self._tasks.discard(task)

        try:
            # Check if task raised an exception
            exc = task.exception()
            if exc:
                self._failed_count += 1
                logger.error(
                    f"[TASK_MANAGER] Task {task.get_name()} failed with exception: {exc}",
                    exc_info=exc,
                )

                # Call custom error handler if provided
                if on_error:
                    try:
                        on_error(exc)
                    except Exception as handler_exc:
                        logger.error(
                            f"[TASK_MANAGER] Error handler failed: {handler_exc}",
                            exc_info=handler_exc,
                        )
            else:
                self._completed_count += 1
                logger.debug(
                    f"[TASK_MANAGER] Task {task.get_name()} completed successfully "
                    f"(remaining active: {len(self._tasks)})"
                )

        except asyncio.CancelledError:
            logger.debug(f"[TASK_MANAGER] Task {task.get_name()} was cancelled")
        except Exception as e:
            logger.error(
                f"[TASK_MANAGER] Error in task cleanup for {task.get_name()}: {e}",
                exc_info=True,
            )

    def cancel_task_by_name(self, name_pattern: str) -> int:
        """
        Cancel tasks matching the given name pattern.

        Args:
            name_pattern: Task name or pattern to match

        Returns:
            Number of tasks cancelled
        """
        cancelled_count = 0
        for task in list(self._tasks):  # Copy to avoid modification during iteration
            task_name = task.get_name()
            if name_pattern in task_name:
                task.cancel()
                cancelled_count += 1
                logger.info(f"[TASK_MANAGER] Cancelled task: {task_name}")

        return cancelled_count

    async def cancel_all(self, timeout: float = 5.0):
        """
        Cancel all active tasks and wait for them to finish.

        Args:
            timeout: Maximum time to wait for tasks to cancel (seconds)
        """
        if not self._tasks:
            logger.debug("[TASK_MANAGER] No active tasks to cancel")
            return

        logger.info(f"[TASK_MANAGER] Cancelling {len(self._tasks)} active tasks...")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to finish with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True), timeout=timeout
            )
            logger.info("[TASK_MANAGER] All tasks cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                f"[TASK_MANAGER] Timeout waiting for {len(self._tasks)} tasks to cancel"
            )

    def get_stats(self) -> dict:
        """
        Get statistics about managed tasks.

        Returns:
            Dictionary with task statistics
        """
        return {
            "active_tasks": len(self._tasks),
            "total_created": self._task_count,
            "completed": self._completed_count,
            "failed": self._failed_count,
            "success_rate": (
                self._completed_count / max(1, self._task_count - len(self._tasks))
            )
            * 100,
        }


# Global singleton instance
_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    """Get the global TaskManager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
