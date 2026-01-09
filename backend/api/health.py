"""Health check endpoints with detailed system metrics."""
from fastapi import APIRouter, HTTPException
import psutil
import time
import logging
from datetime import datetime
from sqlalchemy import text

from backend.core.task_manager import get_task_manager
from backend.sessions.session_registry import get_session_registry
from backend.core.database import AsyncSessionLocal

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)

# Track server start time
_start_time = time.time()


@router.get("/detailed")
async def detailed_health():
    """
    Comprehensive health check with system metrics.

    Returns:
        - status: Overall health status
        - active_sessions: Number of active sessions
        - database: Database connection status
        - memory_mb: Current memory usage in MB
        - uptime_seconds: Server uptime in seconds
        - task_stats: Background task statistics
        - cleanup_stats: Session cleanup statistics
    """
    try:
        # Get session registry stats
        registry = get_session_registry()
        cleanup_stats = registry.get_cleanup_stats()

        # Get task manager stats
        task_manager = get_task_manager()
        task_stats = task_manager.get_stats()

        # Check database connection
        db_status = "ok"
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
        except Exception as e:
            db_status = f"error: {str(e)}"
            logger.error(f"[HEALTH] Database check failed: {e}")

        # Get memory usage
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024

        # Calculate uptime
        uptime_seconds = time.time() - _start_time

        return {
            "status": "healthy" if db_status == "ok" else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "active_sessions": cleanup_stats["active_sessions"],
            "database": db_status,
            "memory_mb": round(memory_mb, 2),
            "uptime_seconds": round(uptime_seconds, 2),
            "task_stats": {
                "active_tasks": task_stats["active_tasks"],
                "total_created": task_stats["total_created"],
                "completed": task_stats["completed"],
                "failed": task_stats["failed"],
                "success_rate": round(task_stats["success_rate"], 2),
            },
            "cleanup_stats": {
                "active_sessions": cleanup_stats["active_sessions"],
                "total_cleaned": cleanup_stats["total_cleaned"],
                "session_timeout_seconds": cleanup_stats["session_timeout_seconds"],
                "oldest_session_age_seconds": round(
                    cleanup_stats["oldest_session_age_seconds"], 2
                ),
            },
        }

    except Exception as e:
        logger.error(f"[HEALTH] Error in detailed health check: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}",
        )


@router.get("/liveness")
async def liveness():
    """
    Basic liveness probe for container orchestration.
    Returns 200 if server is running.
    """
    return {"status": "alive"}


@router.get("/readiness")
async def readiness():
    """
    Readiness probe for container orchestration.
    Checks if server is ready to handle requests.
    """
    try:
        # Check database connection
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))

        return {"status": "ready"}

    except Exception as e:
        logger.error(f"[HEALTH] Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Not ready: {str(e)}",
        )
