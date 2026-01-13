"""
Background task queue for non-blocking operations.

This module provides a simple async task queue for operations that should not block
the main execution path, such as message persistence during streaming.
"""

import asyncio
import logging
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)


class BackgroundTaskQueue:
    """
    A simple background task queue that processes tasks asynchronously.

    Tasks are executed in FIFO order by a single worker coroutine.
    Failed tasks are logged but don't stop the worker.
    """

    def __init__(self, max_queue_size: int = 1000):
        """
        Initialize the background task queue.

        Args:
            max_queue_size: Maximum number of tasks that can be queued.
                           Prevents unbounded memory growth.
        """
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: asyncio.Task | None = None
        self._running = False

        # Metrics
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.tasks_dropped = 0  # Tasks dropped due to full queue

    async def start(self):
        """Start the background worker task."""
        if self._running:
            logger.warning("[BACKGROUND_TASKS] Worker already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("[BACKGROUND_TASKS] Background task worker started")

    async def stop(self):
        """Stop the background worker task gracefully."""
        if not self._running:
            return

        self._running = False

        # Process remaining tasks
        while not self._queue.empty():
            try:
                task = self._queue.get_nowait()
                await task()
            except Exception as e:
                logger.error(f"[BACKGROUND_TASKS] Error processing remaining task: {e}")

        # Cancel worker
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("[BACKGROUND_TASKS] Background task worker stopped")

    async def _worker(self):
        """Worker coroutine that processes tasks from the queue."""
        logger.info("[BACKGROUND_TASKS] Worker started processing tasks")

        while self._running:
            try:
                # Wait for next task
                task = await self._queue.get()

                try:
                    await task()
                    self.tasks_completed += 1
                except Exception as e:
                    self.tasks_failed += 1
                    logger.error(f"[BACKGROUND_TASKS] Task failed: {e}", exc_info=True)
                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                logger.info("[BACKGROUND_TASKS] Worker cancelled")
                break
            except Exception as e:
                logger.error(f"[BACKGROUND_TASKS] Worker error: {e}", exc_info=True)

        logger.info("[BACKGROUND_TASKS] Worker stopped")

    def enqueue(self, coro: Callable[[], Coroutine[Any, Any, None]]):
        """
        Enqueue a coroutine function to be executed in the background.

        Args:
            coro: A callable that returns a coroutine (async function)

        Note:
            If the queue is full, the task will be dropped and tasks_dropped
            will be incremented.
        """
        try:
            self._queue.put_nowait(coro)
        except asyncio.QueueFull:
            self.tasks_dropped += 1
            logger.warning(
                f"[BACKGROUND_TASKS] Queue full (size={self._queue.qsize()}), "
                f"dropping task. Total dropped: {self.tasks_dropped}"
            )

    def get_metrics(self) -> dict:
        """
        Get current queue metrics.

        Returns:
            Dictionary with queue statistics
        """
        total_tasks = self.tasks_completed + self.tasks_failed
        success_rate = (
            self.tasks_completed / total_tasks if total_tasks > 0 else 0.0
        )

        return {
            "queue_size": self._queue.qsize(),
            "max_queue_size": self._queue.maxsize,
            "completed": self.tasks_completed,
            "failed": self.tasks_failed,
            "dropped": self.tasks_dropped,
            "success_rate": success_rate,
            "running": self._running,
        }


# Global instance
_background_tasks: BackgroundTaskQueue | None = None


def get_background_tasks() -> BackgroundTaskQueue:
    """Get the global background task queue instance."""
    global _background_tasks
    if _background_tasks is None:
        _background_tasks = BackgroundTaskQueue()
    return _background_tasks


async def start_background_tasks():
    """Start the global background task queue."""
    queue = get_background_tasks()
    await queue.start()


async def stop_background_tasks():
    """Stop the global background task queue."""
    queue = get_background_tasks()
    await queue.stop()
