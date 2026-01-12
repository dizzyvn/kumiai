"""
Database retry utilities for handling transient lock failures.

Provides decorators and utilities for retrying database operations
that fail due to lock contention with exponential backoff.
"""

import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Any
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

T = TypeVar('T')


class DatabaseRetryConfig:
    """Configuration for database retry behavior."""

    # Maximum number of retry attempts
    MAX_RETRIES = 3

    # Initial delay in seconds before first retry
    INITIAL_DELAY = 0.1

    # Maximum delay between retries in seconds
    MAX_DELAY = 2.0

    # Exponential backoff multiplier
    BACKOFF_MULTIPLIER = 2.0


def is_lock_error(error: Exception) -> bool:
    """
    Check if error is a database lock error that should be retried.

    Args:
        error: Exception to check

    Returns:
        True if error is retryable lock error, False otherwise
    """
    if isinstance(error, OperationalError):
        error_msg = str(error).lower()
        # SQLite lock errors
        lock_errors = [
            'database is locked',
            'database locked',
            'attempt to write a readonly database',
            'disk i/o error',
        ]
        return any(lock_err in error_msg for lock_err in lock_errors)

    return False


async def retry_on_lock(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = DatabaseRetryConfig.MAX_RETRIES,
    initial_delay: float = DatabaseRetryConfig.INITIAL_DELAY,
    max_delay: float = DatabaseRetryConfig.MAX_DELAY,
    backoff_multiplier: float = DatabaseRetryConfig.BACKOFF_MULTIPLIER,
    operation_name: str = "database operation",
    **kwargs: Any
) -> T:
    """
    Retry an async function with exponential backoff on lock errors.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries
        backoff_multiplier: Exponential backoff multiplier
        operation_name: Human-readable operation name for logging
        **kwargs: Keyword arguments for func

    Returns:
        Result from successful function call

    Raises:
        Last exception if all retries exhausted
    """
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            return await func(*args, **kwargs)

        except Exception as e:
            last_error = e

            # Check if this is a retryable lock error
            if not is_lock_error(e):
                # Not a lock error, don't retry
                logger.debug(f"[DB_RETRY] Non-retryable error in {operation_name}: {type(e).__name__}")
                raise

            # Check if we have retries left
            if attempt >= max_retries:
                logger.error(
                    f"[DB_RETRY] Exhausted all {max_retries} retries for {operation_name} - "
                    f"final error: {type(e).__name__}: {e}"
                )
                raise

            # Log retry attempt
            logger.warning(
                f"[DB_RETRY] Lock error in {operation_name} (attempt {attempt + 1}/{max_retries + 1}), "
                f"retrying in {delay:.2f}s - error: {type(e).__name__}: {str(e)[:100]}"
            )

            # Wait with exponential backoff
            await asyncio.sleep(delay)

            # Increase delay for next retry, capped at max_delay
            delay = min(delay * backoff_multiplier, max_delay)

    # Should never reach here, but for type safety
    raise last_error or RuntimeError("Unexpected retry loop exit")


def with_db_retry(
    max_retries: int = DatabaseRetryConfig.MAX_RETRIES,
    initial_delay: float = DatabaseRetryConfig.INITIAL_DELAY,
    max_delay: float = DatabaseRetryConfig.MAX_DELAY,
    backoff_multiplier: float = DatabaseRetryConfig.BACKOFF_MULTIPLIER,
    operation_name: str | None = None,
):
    """
    Decorator to add retry logic to async database operations.

    Usage:
        @with_db_retry(operation_name="persist user messages")
        async def _persist_user_messages(self, messages):
            async with AsyncSessionLocal() as db:
                # ... database operations ...
                await db.commit()

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries
        backoff_multiplier: Exponential backoff multiplier
        operation_name: Human-readable operation name (defaults to function name)

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation_name or func.__name__

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_on_lock(
                func,
                *args,
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                backoff_multiplier=backoff_multiplier,
                operation_name=op_name,
                **kwargs
            )

        return wrapper

    return decorator
