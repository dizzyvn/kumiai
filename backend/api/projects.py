"""Project API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from functools import lru_cache
import uuid
import logging
import os
from pathlib import Path
import shutil

from ..core.database import get_db
from ..models.database import Project, DEFAULT_PROJECT_ID
from ..models.schemas import (
    ProjectMetadata,
    CreateProjectRequest,
    UpdateProjectRequest,
    SpawnAgentRequest,
    FileContentRequest,
    FileContentResponse,
)
from ..services.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectMetadata])
async def list_projects(
    include_archived: bool = False, db: AsyncSession = Depends(get_db)
):
    """Get all projects, excluding the default project."""
    query = select(Project).where(Project.id != DEFAULT_PROJECT_ID)
    if not include_archived:
        query = query.where(Project.is_archived == False)

    result = await db.execute(query.order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    return [
        ProjectMetadata(
            id=p.id,
            name=p.name,
            description=p.description,
            path=p.path,
            pm_id=p.pm_id,
            team_member_ids=p.team_member_ids,
            created_at=p.created_at,
            updated_at=p.updated_at,
            is_archived=p.is_archived,
        )
        for p in projects
    ]


@router.post("", response_model=ProjectMetadata, status_code=201)
async def create_project(
    request: CreateProjectRequest, db: AsyncSession = Depends(get_db)
):
    """Create a new project and spawn its PM session."""
    from ..utils.slug import generate_unique_id
    logger.info(f"Creating new project: {request.name} with PM: {request.pm_id}")

    # Generate human-readable ID if not provided
    if request.id:
        project_id = request.id
    else:
        # Generate slug from name (e.g., "E-commerce Platform" -> "ecommerce-platform-b7c3")
        project_id = generate_unique_id(request.name, suffix_length=4)

    # Check if project already exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Project with this ID already exists")

    # Generate path if not provided - use ~/projects as default
    from pathlib import Path as PathLib
    project_path = request.path or str(PathLib.home() / "projects" / project_id)

    # Create project directory on filesystem
    try:
        Path(project_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created project directory: {project_path}")
    except Exception as e:
        logger.error(f"Failed to create project directory {project_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create project directory: {e}")

    # Create new project
    new_project = Project(
        id=project_id,
        name=request.name,
        description=request.description,
        path=project_path,
        pm_id=request.pm_id,
        team_member_ids=request.team_member_ids,
    )

    # Validate PM character exists before creating project
    if request.pm_id:
        from ..utils.character_file import load_character_from_file

        try:
            logger.debug(f"Validating PM character: {request.pm_id}")
            pm_character = await load_character_from_file(request.pm_id)
            if pm_character is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"PM character '{request.pm_id}' not found in character_library/",
                )
            logger.info(f"PM character '{pm_character.name}' validated successfully")
        except ValueError as e:
            # Character file exists but is malformed
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error validating PM character: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to validate PM character: {e}"
            )

    # Add and commit project FIRST so PM session can reference it via foreign key
    # (PM session creates its own db session and can't see uncommitted data)
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)
    logger.info(f"Project committed to database: {project_id}")

    # Auto-spawn PM session for this project using unified architecture
    # If PM creation fails, we'll delete the project below
    try:
        logger.info(f"Starting PM session creation for project {project_id}")
        from ..config.session_roles import SessionRole
        from ..sessions import get_session_registry
        from ..models.database import AgentInstance as DBAgentInstance

        # Generate instance ID for PM session
        pm_instance_id = f"pm-{uuid.uuid4().hex[:8]}"
        logger.debug(f"Generated PM instance_id: {pm_instance_id}")

        # Generate PROJECT.md for PM
        from ..utils.context_files import generate_project_md
        await generate_project_md(
            project_path=project_path,
            project_id=project_id,
            project_name=new_project.name,
            project_description=new_project.description,
            team_member_ids=new_project.team_member_ids,
            pm_character_id=new_project.pm_id,
        )

        # Create stub database record immediately so frontend can see it
        # This will be updated when background initialization completes
        from backend.core.database import AsyncSessionLocal
        from backend.models.database import AgentInstance as DBAgentInstance
        async with AsyncSessionLocal() as stub_db:
            stub_record = DBAgentInstance(
                instance_id=pm_instance_id,
                session_id=None,  # Will be set after initialization
                character_id=new_project.pm_id,
                project_id=project_id,
                project_path=project_path,
                role="pm",
                status="initializing",  # Special status to indicate background init in progress
                actual_tools=[],
                actual_mcp_servers=[],
            )
            stub_db.add(stub_record)
            await stub_db.commit()
            logger.info(f"Created stub database record for PM session {pm_instance_id}")

        # Schedule PM session creation in background (non-blocking)
        # This prevents slow/hung session initialization from blocking the API response
        logger.debug(f"Scheduling PM session creation in background")
        from backend.core.task_manager import get_task_manager
        task_manager = get_task_manager()

        async def create_pm_session_background():
            """Background task to create PM session"""
            try:
                registry = get_session_registry()
                session = await registry.get_or_create_session(
                    instance_id=pm_instance_id,
                    role=SessionRole.PM,
                    project_path=project_path,
                    character_id=new_project.pm_id,
                    specialists=None,
                    project_id=project_id,
                )
                logger.info(f"Successfully created PM session {pm_instance_id} for project {project_id}")
            except Exception as e:
                logger.error(f"Background PM session creation failed for {project_id}: {e}")
                # Update instance status to error
                from backend.core.database import AsyncSessionLocal
                from backend.models.database import AgentInstance
                from sqlalchemy import update
                async with AsyncSessionLocal() as db_error:
                    await db_error.execute(
                        update(AgentInstance)
                        .where(AgentInstance.instance_id == pm_instance_id)
                        .values(status="error")
                    )
                    await db_error.commit()

        # Create background task (non-blocking)
        task_manager.create_task(
            create_pm_session_background(),
            name=f"create_pm_session_{pm_instance_id}"
        )
        logger.info(f"PM session creation scheduled in background for {pm_instance_id}")

        # Update project with PM instance ID
        new_project.pm_instance_id = pm_instance_id
        await db.commit()
        await db.refresh(new_project)  # Refresh to load all fields after final commit
        logger.debug(f"Updated project {project_id} with pm_instance_id: {pm_instance_id}")

    except Exception as e:
        logger.error(f"Failed to create PM for project {project_id}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")

        # Delete the project since PM creation failed
        logger.info(f"Deleting project {project_id} due to PM creation failure")
        try:
            # Delete the project that was already committed
            await db.delete(new_project)
            await db.commit()
            logger.info(f"Project deleted successfully")
        except Exception as del_err:
            logger.error(f"Failed to delete project: {del_err}")
            await db.rollback()

        # Also delete any orphaned PM session if it was partially created
        try:
            from sqlalchemy import delete
            from ..models.database import AgentInstance as DBAgentInstance
            from ..core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                # Delete any PM sessions for this project
                deleted = await cleanup_db.execute(
                    delete(DBAgentInstance).where(
                        DBAgentInstance.project_id == project_id
                    )
                )
                await cleanup_db.commit()
                logger.info(f"Cleaned up {deleted.rowcount} orphaned PM sessions")
        except Exception as cleanup_err:
            logger.error(f"Failed to cleanup PM session: {cleanup_err}")

        # Return clear error to user
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create PM session: {str(e)}. Project creation rolled back.",
        )

    return ProjectMetadata(
        id=new_project.id,
        name=new_project.name,
        description=new_project.description,
        path=new_project.path,
        pm_id=new_project.pm_id,
        team_member_ids=new_project.team_member_ids,
        created_at=new_project.created_at,
        updated_at=new_project.updated_at,
        is_archived=new_project.is_archived,
    )


@router.get("/{project_id}", response_model=ProjectMetadata)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectMetadata(
        id=project.id,
        name=project.name,
        description=project.description,
        path=project.path,
        pm_id=project.pm_id,
        team_member_ids=project.team_member_ids,
        created_at=project.created_at,
        updated_at=project.updated_at,
        is_archived=project.is_archived,
    )


@router.put("/{project_id}", response_model=ProjectMetadata)
async def update_project(
    project_id: str, request: UpdateProjectRequest, db: AsyncSession = Depends(get_db)
):
    """Update a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Don't allow modifying the default project's ID or archiving it
    if project_id == DEFAULT_PROJECT_ID and request.is_archived:
        raise HTTPException(
            status_code=400, detail="Cannot archive the default project"
        )

    # Update fields
    if request.name is not None:
        project.name = request.name
    if request.description is not None:
        project.description = request.description
    if request.pm_id is not None:
        project.pm_id = request.pm_id
    if request.team_member_ids is not None:
        project.team_member_ids = request.team_member_ids
    if request.is_archived is not None:
        project.is_archived = request.is_archived

    await db.commit()
    await db.refresh(project)

    return ProjectMetadata(
        id=project.id,
        name=project.name,
        description=project.description,
        path=project.path,
        pm_id=project.pm_id,
        team_member_ids=project.team_member_ids,
        created_at=project.created_at,
        updated_at=project.updated_at,
        is_archived=project.is_archived,
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Archive a project (soft delete)."""
    # Don't allow deleting the default project
    if project_id == DEFAULT_PROJECT_ID:
        raise HTTPException(status_code=400, detail="Cannot delete the default project")

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Archive instead of hard delete
    project.is_archived = True
    await db.commit()


@router.post("/{project_id}/unarchive", status_code=200)
async def unarchive_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Unarchive a project."""
    # Don't allow unarchiving the default project (it should never be archived)
    if project_id == DEFAULT_PROJECT_ID:
        raise HTTPException(status_code=400, detail="Cannot unarchive the default project")

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.is_archived:
        raise HTTPException(status_code=400, detail="Project is not archived")

    project.is_archived = False
    await db.commit()

    return {"message": "Project unarchived successfully", "project_id": project_id}


@router.delete("/{project_id}/permanent", status_code=204)
async def hard_delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Permanently delete a project from the database.

    This will:
    1. Delete all associated sessions from the database
    2. Delete the project record from the database

    Note: Project files on disk are NOT deleted and remain accessible.
    WARNING: This action cannot be undone.
    """
    from sqlalchemy import delete
    from ..models.database import AgentInstance as DBAgentInstance

    # Don't allow deleting the default project
    if project_id == DEFAULT_PROJECT_ID:
        raise HTTPException(status_code=400, detail="Cannot delete the default project")

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # 1. Delete all associated sessions from database
        await db.execute(
            delete(DBAgentInstance).where(DBAgentInstance.project_id == project_id)
        )

        # 2. Delete project record from database (files remain on disk)
        await db.delete(project)
        await db.commit()

        logger.info(f"Permanently deleted project from database: {project_id} (files preserved at {project.path})")

    except Exception as e:
        await db.rollback()
        logger.error(f"Error permanently deleting project {project_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to permanently delete project: {str(e)}"
        )


@router.post("/{project_id}/recreate-pm", status_code=200)
async def recreate_pm_session(project_id: str, db: AsyncSession = Depends(get_db)):
    """Recreate the PM session for a project.

    This deletes the existing PM session and creates a fresh one.
    Useful when the PM session is in a broken state (e.g., conversation not found).
    """
    logger.info(f"Recreating PM session for project: {project_id}")

    # Get the project
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete existing PM session
    try:
        from sqlalchemy import delete
        from ..models.database import AgentInstance as DBAgentInstance
        from ..core.database import AsyncSessionLocal
        from ..sessions import get_session_registry

        # Find and delete PM session from database
        async with AsyncSessionLocal() as cleanup_db:
            result = await cleanup_db.execute(
                select(DBAgentInstance).where(
                    DBAgentInstance.project_id == project_id,
                    DBAgentInstance.role == "pm"
                )
            )
            pm_sessions = result.scalars().all()

            if pm_sessions:
                logger.info(f"Found {len(pm_sessions)} existing PM session(s) for project {project_id}")

                # Remove from registry first
                registry = get_session_registry()
                for pm_session in pm_sessions:
                    removed = registry.remove_session(pm_session.instance_id)
                    if removed:
                        logger.info(f"Removed PM session from registry: {pm_session.instance_id}")
                    else:
                        logger.debug(f"PM session not in registry (already cleaned up): {pm_session.instance_id}")

                # Delete all PM sessions from database
                deleted = await cleanup_db.execute(
                    delete(DBAgentInstance).where(
                        DBAgentInstance.project_id == project_id,
                        DBAgentInstance.role == "pm"
                    )
                )

                # Clear pm_instance_id from project
                project_result = await cleanup_db.execute(
                    select(Project).where(Project.id == project_id)
                )
                project_to_clear = project_result.scalar_one_or_none()
                if project_to_clear:
                    project_to_clear.pm_instance_id = None
                    logger.info(f"Cleared pm_instance_id from project {project_id}")

                await cleanup_db.commit()
                logger.info(f"Deleted {deleted.rowcount} PM session(s) from database")
            else:
                logger.info("No existing PM session found - will create new one")

    except Exception as e:
        logger.error(f"Error deleting existing PM session: {e}")
        # Continue anyway - we'll try to create a new one

    # Create new PM session (same logic as in create_project)
    try:
        logger.info(f"Creating new PM session for project {project_id}")
        from ..config.session_roles import SessionRole
        from ..sessions import get_session_registry

        # Generate new instance ID for PM session
        pm_instance_id = f"pm-{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated new PM instance_id: {pm_instance_id}")

        # Regenerate PROJECT.md for PM
        from ..utils.context_files import generate_project_md
        await generate_project_md(
            project_path=project.path,
            project_id=project.id,
            project_name=project.name,
            project_description=project.description,
            team_member_ids=project.team_member_ids,
            pm_character_id=project.pm_id,
        )

        # Update project with new PM instance ID first
        project.pm_instance_id = pm_instance_id
        await db.commit()
        logger.debug(f"Updated project {project_id} with pm_instance_id: {pm_instance_id}")

        # Create stub database record immediately so frontend can see it
        # This will be updated when background initialization completes
        from backend.core.database import AsyncSessionLocal
        from backend.models.database import AgentInstance as DBAgentInstance
        async with AsyncSessionLocal() as stub_db:
            stub_record = DBAgentInstance(
                instance_id=pm_instance_id,
                session_id=None,  # Will be set after initialization
                character_id=project.pm_id,
                project_id=project.id,
                project_path=project.path,
                role="pm",
                status="initializing",  # Special status to indicate background init in progress
                actual_tools=[],
                actual_mcp_servers=[],
            )
            stub_db.add(stub_record)
            await stub_db.commit()
            logger.info(f"Created stub database record for PM session {pm_instance_id}")

        # Schedule session creation in background (non-blocking)
        from backend.core.task_manager import get_task_manager
        task_manager = get_task_manager()

        async def create_pm_session_background():
            """Background task to create PM session"""
            try:
                registry = get_session_registry()
                session = await registry.get_or_create_session(
                    instance_id=pm_instance_id,
                    role=SessionRole.PM,
                    project_path=project.path,
                    character_id=project.pm_id,
                    specialists=None,
                    project_id=project.id,
                )
                logger.info(f"Successfully created new PM session {pm_instance_id} for project {project_id}")
            except Exception as e:
                logger.error(f"Background PM session creation failed for {project_id}: {e}")
                # Update instance status to error
                from backend.core.database import AsyncSessionLocal
                from backend.models.database import AgentInstance
                from sqlalchemy import update
                async with AsyncSessionLocal() as db_error:
                    await db_error.execute(
                        update(AgentInstance)
                        .where(AgentInstance.instance_id == pm_instance_id)
                        .values(status="error")
                    )
                    await db_error.commit()

        task_manager.create_task(
            create_pm_session_background(),
            name=f"recreate_pm_session_{pm_instance_id}"
        )
        logger.info(f"PM session recreation scheduled in background for {pm_instance_id}")

        return {
            "status": "success",
            "message": f"PM session recreated successfully",
            "pm_instance_id": pm_instance_id
        }

    except Exception as e:
        logger.error(f"Failed to recreate PM session for project {project_id}: {e}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to recreate PM session: {str(e)}"
        )


# ============================================================================
# Project File Management Endpoints
# ============================================================================

# Read-only paths in project context
PROJECT_READONLY_PATHS = {".sessions"}

# Common directories/files to ignore (reduces file count by 70-90%)
IGNORE_PATTERNS = {
    'node_modules', '.git', '__pycache__', 'dist', 'build',
    '.next', 'target', '.venv', 'venv', 'coverage', '.pytest_cache',
    '.tox', '.eggs', '*.egg-info', '.cache', '.mypy_cache',
    '.ruff_cache', '.turbo', 'out', '.vercel', '.nuxt', '.output'
}


def is_project_readonly(file_path: str) -> bool:
    """Check if a file/directory is read-only in project context."""
    parts = Path(file_path).parts
    if not parts:
        return False

    # Check if path is within .sessions/ directory
    if parts[0] in PROJECT_READONLY_PATHS:
        return True

    return False


@router.get("/{project_id}/files/content", response_model=FileContentResponse)
async def get_project_file_content(
    project_id: str,
    file_path: str = Query(..., description="Relative path to file within project directory"),
    db: AsyncSession = Depends(get_db)
):
    """Get content of a specific file in project directory."""
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Determine if path is absolute or relative
    path_obj = Path(file_path)
    project_dir = Path(project.path)

    if path_obj.is_absolute():
        # Absolute path - allow reading from anywhere (read-only operation)
        target_file = path_obj
        logger.info(f"[PROJECT_FILE] Using absolute path: {target_file}")

        # Just check if file exists (no project directory restriction for viewing)
        if not target_file.exists():
            logger.warning(f"[PROJECT_FILE] File does not exist: {target_file}")
            raise HTTPException(status_code=404, detail="File not found")

        logger.info(f"[PROJECT_FILE] ✓ Absolute path allowed for viewing: {target_file}")
    else:
        # Relative path - resolve within project directory
        target_file = project_dir / file_path

        # Security check: ensure file is within project directory OR is a valid symlink to character library
        try:
            logger.debug(f"[PROJECT_FILE] Checking relative path file: {target_file}")
            logger.debug(f"[PROJECT_FILE] Project dir: {project_dir.resolve()}")
            logger.debug(f"[PROJECT_FILE] File exists: {target_file.exists()}")

            # Check if file exists first to provide better error message
            if not target_file.exists():
                logger.warning(f"[PROJECT_FILE] File does not exist: {target_file}")
                raise HTTPException(status_code=404, detail="File not found")

            resolved_path = target_file.resolve()
            logger.debug(f"[PROJECT_FILE] Resolved path: {resolved_path}")

            # First try: is it within the project directory?
            try:
                relative_path = resolved_path.relative_to(project_dir.resolve())
                logger.debug(f"[PROJECT_FILE] ✓ File is within project directory: {relative_path}")
            except ValueError:
                # Not in project dir - check if it's a symlink pointing to character_library
                if target_file.is_symlink():
                    from ..core.config import settings
                    characters_dir = settings.characters_dir.resolve()
                    logger.debug(f"[PROJECT_FILE] File is a symlink, checking character library")

                    # Allow if symlink target is within character_library
                    try:
                        resolved_path.relative_to(characters_dir)
                        logger.debug(f"[PROJECT_FILE] ✓ Symlink to character library: {target_file} -> {resolved_path}")
                    except ValueError:
                        logger.warning(f"[PROJECT_FILE] ✗ Symlink points outside allowed directories: {target_file} -> {resolved_path}")
                        raise HTTPException(status_code=403, detail=f"Access denied: symlink points outside allowed directories. Target: {resolved_path}")
                else:
                    logger.warning(f"[PROJECT_FILE] ✗ Path outside project directory: {resolved_path}")
                    logger.warning(f"[PROJECT_FILE]   Requested path: {file_path}")
                    logger.warning(f"[PROJECT_FILE]   Resolved path: {resolved_path}")
                    logger.warning(f"[PROJECT_FILE]   Project dir: {project_dir.resolve()}")
                    raise HTTPException(status_code=403, detail=f"Access denied: path is outside project directory. Requested: {file_path}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[PROJECT_FILE] Security check failed for {target_file}: {type(e).__name__}: {e}")
            raise HTTPException(status_code=403, detail=f"Access denied: {str(e)}")

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    try:
        content = target_file.read_text(encoding='utf-8')
        return FileContentResponse(
            path=file_path,
            content=content,
            readonly=is_project_readonly(file_path),
        )
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not a text file")
    except Exception as e:
        logger.error(f"Failed to read file {target_file}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@router.put("/{project_id}/files/content", status_code=204)
async def update_project_file_content(
    project_id: str,
    request: FileContentRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update content of a file in project directory.

    Only allows updating files outside .sessions/ directory.
    Session files must be updated via session files API.
    """
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if file is read-only
    if is_project_readonly(request.file_path):
        raise HTTPException(
            status_code=403,
            detail=f"File is read-only: {request.file_path}. Use session files API to edit session files."
        )

    # Construct full path
    project_dir = Path(project.path)
    target_file = project_dir / request.file_path

    # Security check: ensure file is within project directory
    try:
        logger.debug(f"[PROJECT_UPDATE] Checking file: {target_file}")
        resolved_path = target_file.resolve()
        resolved_path.relative_to(project_dir.resolve())
        logger.debug(f"[PROJECT_UPDATE] ✓ File is within project directory")
    except ValueError:
        logger.warning(f"[PROJECT_UPDATE] ✗ Path outside project directory")
        logger.warning(f"[PROJECT_UPDATE]   Requested path: {request.file_path}")
        logger.warning(f"[PROJECT_UPDATE]   Project dir: {project_dir.resolve()}")
        raise HTTPException(status_code=403, detail=f"Access denied: path is outside project directory. Requested: {request.file_path}")

    try:
        # Create parent directories if needed
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        target_file.write_text(request.content, encoding='utf-8')
        logger.info(f"Updated file: {target_file}")

    except Exception as e:
        logger.error(f"Failed to write file {target_file}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")


@router.delete("/{project_id}/files", status_code=204)
async def delete_project_file(
    project_id: str,
    file_path: str = Query(..., description="Relative path to file/directory within project directory"),
    db: AsyncSession = Depends(get_db)
):
    """Delete a file or directory in project directory.

    Only allows deleting files/directories outside .sessions/.
    Cannot delete PROJECT.md.
    """
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if file/directory is read-only
    if is_project_readonly(file_path):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot delete protected path: {file_path}"
        )

    # Don't allow deleting PROJECT.md
    if Path(file_path).name == "PROJECT.md":
        raise HTTPException(
            status_code=403,
            detail="Cannot delete PROJECT.md"
        )

    # Construct full path
    project_dir = Path(project.path)
    target_path = project_dir / file_path

    # Security check: ensure path is within project directory
    try:
        logger.debug(f"[PROJECT_DELETE] Checking path: {target_path}")
        resolved_path = target_path.resolve()
        resolved_path.relative_to(project_dir.resolve())
        logger.debug(f"[PROJECT_DELETE] ✓ Path is within project directory")
    except ValueError:
        logger.warning(f"[PROJECT_DELETE] ✗ Path outside project directory")
        logger.warning(f"[PROJECT_DELETE]   Requested path: {file_path}")
        logger.warning(f"[PROJECT_DELETE]   Project dir: {project_dir.resolve()}")
        raise HTTPException(status_code=403, detail=f"Access denied: path is outside project directory. Requested: {file_path}")

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    try:
        if target_path.is_file():
            target_path.unlink()
            logger.info(f"Deleted file: {target_path}")
        elif target_path.is_dir():
            shutil.rmtree(target_path)
            logger.info(f"Deleted directory: {target_path}")

    except Exception as e:
        logger.error(f"Failed to delete {target_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


@router.get("/{project_id}/files/download")
async def download_project_file(
    project_id: str,
    file_path: str = Query(..., description="Relative path to file within project directory"),
    db: AsyncSession = Depends(get_db)
):
    """Download a file from project directory."""
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Determine if path is absolute or relative
    path_obj = Path(file_path)
    project_dir = Path(project.path)

    if path_obj.is_absolute():
        # Absolute path - allow downloading from anywhere (read-only operation)
        target_file = path_obj
        logger.info(f"[PROJECT_DOWNLOAD] Using absolute path: {target_file}")

        # Just check if file exists (no project directory restriction for downloading)
        if not target_file.exists():
            logger.warning(f"[PROJECT_DOWNLOAD] File does not exist: {target_file}")
            raise HTTPException(status_code=404, detail="File not found")

        logger.info(f"[PROJECT_DOWNLOAD] ✓ Absolute path allowed for downloading: {target_file}")
    else:
        # Relative path - resolve within project directory
        target_file = project_dir / file_path

        # Security check: ensure file is within project directory
        try:
            logger.debug(f"[PROJECT_DOWNLOAD] Checking relative path file: {target_file}")
            logger.debug(f"[PROJECT_DOWNLOAD] Project dir: {project_dir.resolve()}")
            logger.debug(f"[PROJECT_DOWNLOAD] File exists: {target_file.exists()}")

            # Check if file exists first to provide better error message
            if not target_file.exists():
                logger.warning(f"[PROJECT_DOWNLOAD] File does not exist: {target_file}")
                raise HTTPException(status_code=404, detail="File not found")

            resolved_path = target_file.resolve()
            logger.debug(f"[PROJECT_DOWNLOAD] Resolved path: {resolved_path}")

            relative_path = resolved_path.relative_to(project_dir.resolve())
            logger.debug(f"[PROJECT_DOWNLOAD] ✓ File is within project directory: {relative_path}")
        except HTTPException:
            raise
        except ValueError:
            logger.warning(f"[PROJECT_DOWNLOAD] ✗ Path outside project directory: {target_file.resolve()}")
            logger.warning(f"[PROJECT_DOWNLOAD]   Requested path: {file_path}")
            logger.warning(f"[PROJECT_DOWNLOAD]   Project dir: {project_dir.resolve()}")
            raise HTTPException(status_code=403, detail=f"Access denied: path is outside project directory. Requested: {file_path}")
        except Exception as e:
            logger.error(f"[PROJECT_DOWNLOAD] Security check failed for {target_file}: {type(e).__name__}: {e}")
            raise HTTPException(status_code=403, detail=f"Access denied: {str(e)}")

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    return FileResponse(
        path=str(target_file),
        filename=target_file.name,
        media_type='application/octet-stream'
    )
