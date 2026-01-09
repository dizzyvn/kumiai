"""
Data retention and cleanup utilities.

Manages automatic cleanup of old data to prevent unbounded database growth.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import delete, select

from backend.core.constants import (
    MESSAGE_RETENTION_DAYS,
    COMPLETED_SESSION_RETENTION_DAYS,
    ACTIVITY_LOG_RETENTION_DAYS,
    CLEANUP_HOUR,
    CLEANUP_MINUTE,
)
from backend.core.database import AsyncSessionLocal
from backend.models.database import SessionMessage, AgentInstance, ActivityLog

logger = logging.getLogger(__name__)


async def cleanup_old_messages():
    """Delete messages older than MESSAGE_RETENTION_DAYS."""
    cutoff = datetime.now() - timedelta(days=MESSAGE_RETENTION_DAYS)

    async with AsyncSessionLocal() as db:
        try:
            # Count messages to be deleted
            count_stmt = select(SessionMessage).where(SessionMessage.timestamp < cutoff)
            result = await db.execute(count_stmt)
            messages_to_delete = len(result.all())

            if messages_to_delete == 0:
                logger.info("[CLEANUP] No old messages to delete")
                return 0

            # Delete old messages
            stmt = delete(SessionMessage).where(SessionMessage.timestamp < cutoff)
            await db.execute(stmt)
            await db.commit()

            logger.info(f"[CLEANUP] Deleted {messages_to_delete} messages older than {MESSAGE_RETENTION_DAYS} days")
            return messages_to_delete

        except Exception as e:
            logger.error(f"[CLEANUP] Failed to delete old messages: {e}")
            await db.rollback()
            return 0


async def cleanup_old_sessions():
    """Delete completed/cancelled sessions older than COMPLETED_SESSION_RETENTION_DAYS."""
    cutoff = datetime.now() - timedelta(days=COMPLETED_SESSION_RETENTION_DAYS)

    async with AsyncSessionLocal() as db:
        try:
            # Count sessions to be deleted
            count_stmt = select(AgentInstance).where(
                AgentInstance.status.in_(['completed', 'cancelled', 'error']),
                AgentInstance.started_at < cutoff
            )
            result = await db.execute(count_stmt)
            sessions_to_delete = len(result.all())

            if sessions_to_delete == 0:
                logger.info("[CLEANUP] No old completed sessions to delete")
                return 0

            # Delete old completed/cancelled/error sessions
            # CASCADE will automatically delete related messages and activity logs
            stmt = delete(AgentInstance).where(
                AgentInstance.status.in_(['completed', 'cancelled', 'error']),
                AgentInstance.started_at < cutoff
            )
            await db.execute(stmt)
            await db.commit()

            logger.info(f"[CLEANUP] Deleted {sessions_to_delete} completed sessions older than {COMPLETED_SESSION_RETENTION_DAYS} days")
            return sessions_to_delete

        except Exception as e:
            logger.error(f"[CLEANUP] Failed to delete old sessions: {e}")
            await db.rollback()
            return 0


async def cleanup_old_activity_logs():
    """Delete activity logs older than ACTIVITY_LOG_RETENTION_DAYS."""
    cutoff = datetime.now() - timedelta(days=ACTIVITY_LOG_RETENTION_DAYS)

    async with AsyncSessionLocal() as db:
        try:
            # Count logs to be deleted
            count_stmt = select(ActivityLog).where(ActivityLog.timestamp < cutoff)
            result = await db.execute(count_stmt)
            logs_to_delete = len(result.all())

            if logs_to_delete == 0:
                logger.info("[CLEANUP] No old activity logs to delete")
                return 0

            # Delete old activity logs
            stmt = delete(ActivityLog).where(ActivityLog.timestamp < cutoff)
            await db.execute(stmt)
            await db.commit()

            logger.info(f"[CLEANUP] Deleted {logs_to_delete} activity logs older than {ACTIVITY_LOG_RETENTION_DAYS} days")
            return logs_to_delete

        except Exception as e:
            logger.error(f"[CLEANUP] Failed to delete old activity logs: {e}")
            await db.rollback()
            return 0


async def cleanup_expired_temp_files():
    """Delete temporary upload files older than 1 hour."""
    temp_dir = Path("temp_uploads")

    if not temp_dir.exists():
        logger.info("[CLEANUP] No temp upload directory found")
        return 0

    cutoff_time = datetime.now() - timedelta(hours=1)
    deleted_count = 0

    try:
        for session_dir in temp_dir.iterdir():
            if not session_dir.is_dir():
                continue

            for temp_file in session_dir.iterdir():
                try:
                    file_mtime = datetime.fromtimestamp(temp_file.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        temp_file.unlink()
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"[CLEANUP] Failed to delete temp file {temp_file}: {e}")

            # Remove empty session directories
            try:
                if not any(session_dir.iterdir()):
                    session_dir.rmdir()
            except Exception as e:
                logger.warning(f"[CLEANUP] Failed to remove empty session temp dir {session_dir}: {e}")

        if deleted_count > 0:
            logger.info(f"[CLEANUP] Deleted {deleted_count} expired temp files")

        return deleted_count

    except Exception as e:
        logger.error(f"[CLEANUP] Failed during temp file cleanup: {e}")
        return deleted_count


async def run_cleanup():
    """Run all cleanup tasks."""
    logger.info("[CLEANUP] Starting scheduled cleanup")

    messages_deleted = await cleanup_old_messages()
    sessions_deleted = await cleanup_old_sessions()
    logs_deleted = await cleanup_old_activity_logs()
    temp_files_deleted = await cleanup_expired_temp_files()

    logger.info(
        f"[CLEANUP] Cleanup complete - "
        f"Deleted: {messages_deleted} messages, "
        f"{sessions_deleted} sessions, "
        f"{logs_deleted} activity logs, "
        f"{temp_files_deleted} temp files"
    )


async def schedule_daily_cleanup():
    """
    Schedule cleanup to run daily at configured time (default: 2 AM).

    This function runs indefinitely and should be started as a background task.
    """
    while True:
        try:
            # Calculate time until next cleanup time
            now = datetime.now()
            next_run = now.replace(hour=CLEANUP_HOUR, minute=CLEANUP_MINUTE, second=0, microsecond=0)

            # If it's past cleanup time today, schedule for tomorrow
            if now.hour >= CLEANUP_HOUR:
                next_run += timedelta(days=1)

            # Wait until next scheduled time
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"[CLEANUP] Next cleanup scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({wait_seconds/3600:.1f} hours)")

            await asyncio.sleep(wait_seconds)

            # Run cleanup
            await run_cleanup()

        except asyncio.CancelledError:
            logger.info("[CLEANUP] Cleanup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"[CLEANUP] Error in cleanup scheduler: {e}")
            # Wait 1 hour before retrying on error
            await asyncio.sleep(3600)
