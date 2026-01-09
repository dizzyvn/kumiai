"""FastAPI application entry point."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import sys
from pathlib import Path
import logging
import asyncio

# Ensure parent directory is in path for package imports
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from backend.core.config import settings
from backend.core.database import init_db
from backend.core.task_manager import get_task_manager
from backend.sessions.session_registry import get_session_registry
from backend.core.cleanup import schedule_daily_cleanup
from backend.api import characters, skills, agents, projects, mcp, session_files, health, robot, user_profile


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    # Ensure ~/.kumiai directory exists
    settings.kumiai_home.mkdir(parents=True, exist_ok=True)
    print(f"✓ KumiAI home directory: {settings.kumiai_home}")

    await init_db()
    print("✓ Database initialized")

    # Reset stuck sessions from previous crash
    from backend.core.database import AsyncSessionLocal
    from backend.models.database import AgentInstance
    from sqlalchemy import update
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(AgentInstance)
            .where(AgentInstance.status.in_(['running', 'thinking', 'working']))
            .values(status='idle')
        )
        await db.commit()
        if result.rowcount > 0:
            print(f"✓ Reset {result.rowcount} stuck sessions to idle")

    # Start background cleanup task
    cleanup_task = asyncio.create_task(schedule_daily_cleanup())
    print("✓ Data retention cleanup scheduled (daily at 2 AM)")

    print(f"✓ Server starting on {settings.api_host}:{settings.api_port}")
    yield
    # Shutdown
    print("⚠️  Server shutting down - cleaning up resources...")

    # Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Gracefully shutdown session registry (cancels all sessions)
    registry = get_session_registry()
    await registry.shutdown()

    # Cancel all background tasks
    task_manager = get_task_manager()
    await task_manager.cancel_all()

    print("✓ Cleanup complete")


# Create FastAPI app
app = FastAPI(
    title="kumiAI Backend",
    description="Multi-agent system backend powered by Claude Agent SDK",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
# Set up root logger with DEBUG level for all application logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Suppress verbose third-party library logs
logging.getLogger('aiosqlite').setLevel(logging.WARNING)
logging.getLogger('watchfiles.main').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# Global exception handler to prevent server crashes
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches all unhandled exceptions to prevent server crashes.
    Logs the error and returns a proper error response to the client.
    """
    logger.error(
        f"Unhandled exception in {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc),
            "path": request.url.path,
        },
    )


# Include routers
app.include_router(characters.router)
app.include_router(skills.router)
app.include_router(agents.router)
app.include_router(projects.router)
app.include_router(mcp.router)
app.include_router(session_files.router)
app.include_router(health.router)
app.include_router(robot.router)
app.include_router(user_profile.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "kumiAI Backend",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="debug",
        # Connection timeouts to prevent CLOSE_WAIT leaks
        timeout_keep_alive=30,
        timeout_graceful_shutdown=15,
        # Limit concurrent connections to prevent resource exhaustion
        limit_concurrency=1000,
        limit_max_requests=10000,
    )
