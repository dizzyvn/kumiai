"""Session files API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from typing import Optional, List
from functools import lru_cache
from datetime import datetime, timedelta
import logging
import os
import shutil
import mimetypes
import uuid

from ..core.database import get_db
from ..services.agent_service import AgentService
from ..models.schemas import (
    FileContentRequest,
    FileContentResponse,
    FilePrepareResponse,
    PreparedFileInfo,
    FileCommitRequest,
    FileCommitResponse,
    CommittedFileInfo,
    FileUploadError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["session-files"])


# Read-only files in session context
READONLY_FILES = {"SESSION.md"}
READONLY_DIRECTORIES = {"agents"}

# Common directories/files to ignore (reduces file count by 70-90%)
IGNORE_PATTERNS = {
    'node_modules', '.git', '__pycache__', 'dist', 'build',
    '.next', 'target', '.venv', 'venv', 'coverage', '.pytest_cache',
    '.tox', '.eggs', '*.egg-info', '.cache', '.mypy_cache',
    '.ruff_cache', '.turbo', 'out', '.vercel', '.nuxt', '.output'
}

# File upload configuration
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB per file
MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500MB total
ALLOWED_UPLOAD_DIRS = {"working", "result"}
BLOCKED_EXTENSIONS = {".exe", ".sh", ".bat", ".dll", ".so", ".dylib", ".app"}

# Temp storage for prepared uploads
TEMP_UPLOAD_DIR = Path("temp_uploads")
TEMP_UPLOAD_DIR.mkdir(exist_ok=True)


def is_readonly(file_path: str) -> bool:
    """Check if a file/directory is read-only in session context."""
    parts = Path(file_path).parts
    if not parts:
        return False

    # Check if any part of the path is in readonly directories
    if any(part in READONLY_DIRECTORIES for part in parts):
        return True

    # Check if filename is in readonly files
    if parts[-1] in READONLY_FILES:
        return True

    return False


@router.get("/{session_id}/files/content", response_model=FileContentResponse)
async def get_session_file_content(
    session_id: str,
    file_path: str = Query(..., description="Relative path to file within session directory"),
    db: AsyncSession = Depends(get_db)
):
    """Get content of a specific file in session directory."""
    # Verify session exists
    service = AgentService(db)
    agent = await service.get_agent(session_id)

    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine if path is absolute or relative
    path_obj = Path(file_path)
    project_path = Path(agent.project_path)

    if path_obj.is_absolute():
        # Absolute path - allow reading from anywhere (read-only operation)
        target_file = path_obj
        logger.info(f"[FILE_ACCESS] Using absolute path: {target_file}")

        # Just check if file exists (no project directory restriction for viewing)
        if not target_file.exists():
            logger.warning(f"[FILE_ACCESS] File does not exist: {target_file}")
            raise HTTPException(status_code=404, detail="File not found")

        logger.info(f"[FILE_ACCESS] ✓ Absolute path allowed for viewing: {target_file}")
    else:
        # Relative path - resolve within session directory
        session_dir = project_path / ".sessions" / session_id
        target_file = session_dir / file_path

        # Security check: ensure file is within session directory OR is a valid symlink to character library
        try:
            logger.debug(f"[FILE_ACCESS] Checking relative path file: {target_file}")
            logger.debug(f"[FILE_ACCESS] Session dir: {session_dir.resolve()}")
            logger.debug(f"[FILE_ACCESS] File exists: {target_file.exists()}")

            # Check if file exists first to provide better error message
            if not target_file.exists():
                logger.warning(f"[FILE_ACCESS] File does not exist: {target_file}")
                raise HTTPException(status_code=404, detail="File not found")

            resolved_path = target_file.resolve()
            logger.debug(f"[FILE_ACCESS] Resolved path: {resolved_path}")

            # First try: is it within the session directory?
            try:
                relative_path = resolved_path.relative_to(session_dir.resolve())
                logger.debug(f"[FILE_ACCESS] ✓ File is within session directory: {relative_path}")
            except ValueError:
                # Not in session dir - check if it's a symlink pointing to character_library
                if target_file.is_symlink():
                    from ..core.config import settings
                    characters_dir = settings.characters_dir.resolve()
                    logger.debug(f"[FILE_ACCESS] File is a symlink, checking character library")

                    # Allow if symlink target is within character_library
                    try:
                        resolved_path.relative_to(characters_dir)
                        logger.debug(f"[FILE_ACCESS] ✓ Symlink to character library: {target_file} -> {resolved_path}")
                    except ValueError:
                        logger.warning(f"[FILE_ACCESS] ✗ Symlink points outside allowed directories: {target_file} -> {resolved_path}")
                        raise HTTPException(status_code=403, detail=f"Access denied: symlink points outside allowed directories. Target: {resolved_path}")
                else:
                    logger.warning(f"[FILE_ACCESS] ✗ Path outside session directory: {resolved_path}")
                    logger.warning(f"[FILE_ACCESS]   Requested path: {file_path}")
                    logger.warning(f"[FILE_ACCESS]   Resolved path: {resolved_path}")
                    logger.warning(f"[FILE_ACCESS]   Session dir: {session_dir.resolve()}")
                    raise HTTPException(status_code=403, detail=f"Access denied: path is outside session directory. Requested: {file_path}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[FILE_ACCESS] Security check failed for {target_file}: {type(e).__name__}: {e}")
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
            readonly=is_readonly(file_path),
        )
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not a text file")
    except Exception as e:
        logger.error(f"Failed to read file {target_file}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@router.put("/{session_id}/files/content", status_code=204)
async def update_session_file_content(
    session_id: str,
    request: FileContentRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update content of a file in session directory.

    Only allows updating files in working/ and result/.
    SESSION.md and agents/ directory are read-only.
    """
    # Verify session exists
    service = AgentService(db)
    agent = await service.get_agent(session_id)

    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if file is read-only
    if is_readonly(request.file_path):
        raise HTTPException(
            status_code=403,
            detail=f"File is read-only: {request.file_path}"
        )

    # Construct full path
    project_path = Path(agent.project_path)
    session_dir = project_path / ".sessions" / session_id
    target_file = session_dir / request.file_path

    # Security check: ensure file is within session directory
    try:
        logger.debug(f"[SESSION_UPDATE] Checking file: {target_file}")
        resolved_path = target_file.resolve()
        resolved_path.relative_to(session_dir.resolve())
        logger.debug(f"[SESSION_UPDATE] ✓ File is within session directory")
    except ValueError:
        logger.warning(f"[SESSION_UPDATE] ✗ Path outside session directory")
        logger.warning(f"[SESSION_UPDATE]   Requested path: {request.file_path}")
        logger.warning(f"[SESSION_UPDATE]   Session dir: {session_dir.resolve()}")
        raise HTTPException(status_code=403, detail=f"Access denied: path is outside session directory. Requested: {request.file_path}")

    try:
        # Create parent directories if needed
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        target_file.write_text(request.content, encoding='utf-8')
        logger.info(f"Updated file: {target_file}")

    except Exception as e:
        logger.error(f"Failed to write file {target_file}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")


@router.delete("/{session_id}/files", status_code=204)
async def delete_session_file(
    session_id: str,
    file_path: str = Query(..., description="Relative path to file/directory within session directory"),
    db: AsyncSession = Depends(get_db)
):
    """Delete a file or directory in session directory.

    Only allows deleting files/directories in working/ and result/.
    SESSION.md and agents/ are protected.
    """
    # Verify session exists
    service = AgentService(db)
    agent = await service.get_agent(session_id)

    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if file/directory is read-only
    if is_readonly(file_path):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot delete protected path: {file_path}"
        )

    # Construct full path
    project_path = Path(agent.project_path)
    session_dir = project_path / ".sessions" / session_id
    target_path = session_dir / file_path

    # Security check: ensure path is within session directory
    try:
        logger.debug(f"[SESSION_DELETE] Checking path: {target_path}")
        resolved_path = target_path.resolve()
        resolved_path.relative_to(session_dir.resolve())
        logger.debug(f"[SESSION_DELETE] ✓ Path is within session directory")
    except ValueError:
        logger.warning(f"[SESSION_DELETE] ✗ Path outside session directory")
        logger.warning(f"[SESSION_DELETE]   Requested path: {file_path}")
        logger.warning(f"[SESSION_DELETE]   Session dir: {session_dir.resolve()}")
        raise HTTPException(status_code=403, detail=f"Access denied: path is outside session directory. Requested: {file_path}")

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


@router.get("/{session_id}/files/download")
async def download_session_file(
    session_id: str,
    file_path: str = Query(..., description="Relative path within session directory or absolute path to any file"),
    db: AsyncSession = Depends(get_db)
):
    """Download a file from session directory or from an absolute path.

    Supports:
    - Relative paths: 'working/file.pdf' (within session directory)
    - Absolute paths: '/absolute/path/to/file.pdf' (anywhere on filesystem)
    """
    # Verify session exists
    service = AgentService(db)
    agent = await service.get_agent(session_id)

    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine if path is absolute or relative
    path_obj = Path(file_path)
    project_path = Path(agent.project_path)

    if path_obj.is_absolute():
        # Absolute path - allow downloading from anywhere (read-only operation)
        target_file = path_obj
        logger.info(f"[DOWNLOAD] Using absolute path: {target_file}")

        # Just check if file exists (no project directory restriction for downloading)
        if not target_file.exists():
            logger.warning(f"[DOWNLOAD] File does not exist: {target_file}")
            raise HTTPException(status_code=404, detail="File not found")

        logger.info(f"[DOWNLOAD] ✓ Absolute path allowed for downloading: {target_file}")
    else:
        # Relative path - resolve within session directory
        session_dir = project_path / ".sessions" / session_id
        target_file = session_dir / file_path

        # Security check: ensure file is within session directory OR is a valid symlink to character library
        try:
            logger.debug(f"[DOWNLOAD] Checking relative path file: {target_file}")
            logger.debug(f"[DOWNLOAD] Session dir: {session_dir.resolve()}")
            logger.debug(f"[DOWNLOAD] File exists: {target_file.exists()}")

            # Check if file exists first to provide better error message
            if not target_file.exists():
                logger.warning(f"[DOWNLOAD] File does not exist: {target_file}")
                raise HTTPException(status_code=404, detail="File not found")

            resolved_path = target_file.resolve()
            logger.debug(f"[DOWNLOAD] Resolved path: {resolved_path}")

            # First try: is it within the session directory?
            try:
                relative_path = resolved_path.relative_to(session_dir.resolve())
                logger.debug(f"[DOWNLOAD] ✓ File is within session directory: {relative_path}")
            except ValueError:
                # Not in session dir - check if it's a symlink pointing to character_library
                if target_file.is_symlink():
                    from ..core.config import settings
                    characters_dir = settings.characters_dir.resolve()
                    logger.debug(f"[DOWNLOAD] File is a symlink, checking character library")

                    # Allow if symlink target is within character_library
                    try:
                        resolved_path.relative_to(characters_dir)
                        logger.debug(f"[DOWNLOAD] ✓ Symlink to character library: {target_file} -> {resolved_path}")
                    except ValueError:
                        logger.warning(f"[DOWNLOAD] ✗ Symlink points outside allowed directories: {target_file} -> {resolved_path}")
                        raise HTTPException(status_code=403, detail=f"Access denied: symlink points outside allowed directories. Target: {resolved_path}")
                else:
                    logger.warning(f"[DOWNLOAD] ✗ Path outside session directory: {resolved_path}")
                    logger.warning(f"[DOWNLOAD]   Requested path: {file_path}")
                    logger.warning(f"[DOWNLOAD]   Resolved path: {resolved_path}")
                    logger.warning(f"[DOWNLOAD]   Session dir: {session_dir.resolve()}")
                    raise HTTPException(status_code=403, detail=f"Access denied: path is outside session directory. Requested: {file_path}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[DOWNLOAD] Security check failed for {target_file}: {type(e).__name__}: {e}")
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


@router.post("/{session_id}/files/prepare", response_model=FilePrepareResponse)
async def prepare_file_upload(
    session_id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Stage 1: Upload files to temporary storage.

    Files are stored temporarily and given a unique ID.
    They will be moved to session directory when commit is called.

    Temp files auto-expire after 1 hour if not committed.

    Returns prepared file info with temp IDs and expiry timestamps.
    """
    # Verify session exists
    service = AgentService(db)
    agent = await service.get_agent(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create temp directory for this session
    session_temp_dir = TEMP_UPLOAD_DIR / session_id
    session_temp_dir.mkdir(parents=True, exist_ok=True)

    prepared = []
    errors = []

    # Validate total size first
    total_size = sum(file.size or 0 for file in files if file.size)
    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Total upload size ({total_size / 1024 / 1024:.1f}MB) exceeds limit ({MAX_TOTAL_SIZE / 1024 / 1024:.0f}MB)"
        )

    for file in files:
        try:
            # Validate file size
            if file.size and file.size > MAX_FILE_SIZE:
                errors.append(FileUploadError(
                    name=file.filename or "unknown",
                    error=f"File size ({file.size / 1024 / 1024:.1f}MB) exceeds {MAX_FILE_SIZE / 1024 / 1024:.0f}MB limit"
                ))
                continue

            # Validate file extension
            file_ext = Path(file.filename or "").suffix.lower()
            if file_ext in BLOCKED_EXTENSIONS:
                errors.append(FileUploadError(
                    name=file.filename or "unknown",
                    error=f"File type {file_ext} not allowed for security reasons"
                ))
                continue

            # Sanitize filename (prevent path traversal)
            safe_filename = Path(file.filename or "unknown").name
            if not safe_filename or safe_filename.startswith('.'):
                errors.append(FileUploadError(
                    name=file.filename or "unknown",
                    error="Invalid filename"
                ))
                continue

            # Generate unique temp ID
            temp_id = f"temp_{uuid.uuid4().hex[:8]}_{safe_filename}"
            temp_path = session_temp_dir / temp_id

            # Stream file to temp storage
            file_size = 0
            with temp_path.open("wb") as buffer:
                while chunk := await file.read(8192):  # 8KB chunks
                    buffer.write(chunk)
                    file_size += len(chunk)

            # Set expiry (1 hour from now)
            expires_at = datetime.utcnow() + timedelta(hours=1)

            prepared.append(PreparedFileInfo(
                id=temp_id,
                name=safe_filename,
                size=file_size,
                type=mimetypes.guess_type(safe_filename)[0] or "application/octet-stream",
                expires_at=expires_at.isoformat() + "Z"
            ))

            logger.info(f"Prepared temp file: {temp_path} ({file_size} bytes, expires: {expires_at})")

        except Exception as e:
            logger.error(f"Failed to prepare {file.filename}: {e}")
            errors.append(FileUploadError(
                name=file.filename or "unknown",
                error=str(e)
            ))

    return FilePrepareResponse(prepared=prepared, errors=errors)


@router.post("/{session_id}/files/commit", response_model=FileCommitResponse)
async def commit_file_upload(
    session_id: str,
    request: FileCommitRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Stage 2: Move prepared files from temp to session directory.

    Call this when user sends the message with attachments.
    Files are moved (not copied) from temp to session folder for efficiency.

    Request body:
    {
        "file_ids": ["temp_abc123_data.json", "temp_def456_config.yaml"],
        "target_dir": "working"  // or "result"
    }

    Returns committed file info with final paths in session.
    """
    # Validate target directory
    if request.target_dir not in ALLOWED_UPLOAD_DIRS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target directory. Must be one of: {', '.join(ALLOWED_UPLOAD_DIRS)}"
        )

    # Verify session exists
    service = AgentService(db)
    agent = await service.get_agent(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get session paths
    project_path = Path(agent.project_path)
    session_dir = project_path / ".sessions" / session_id
    target_path = session_dir / request.target_dir
    target_path.mkdir(parents=True, exist_ok=True)

    session_temp_dir = TEMP_UPLOAD_DIR / session_id

    committed = []
    errors = []

    for file_id in request.file_ids:
        try:
            # Security: Ensure file_id doesn't contain path traversal
            if ".." in file_id or "/" in file_id or "\\" in file_id:
                errors.append(FileUploadError(
                    name=file_id,
                    error="Invalid file ID"
                ))
                continue

            temp_file = session_temp_dir / file_id

            if not temp_file.exists():
                errors.append(FileUploadError(
                    name=file_id,
                    error="Temp file not found or expired"
                ))
                continue

            # Extract original filename from temp_id (format: temp_hash_originalname.ext)
            parts = file_id.split("_", 2)  # Split into ["temp", "hash", "originalname.ext"]
            if len(parts) < 3:
                errors.append(FileUploadError(
                    name=file_id,
                    error="Invalid temp file ID format"
                ))
                continue

            original_name = parts[2]

            # Handle filename conflicts (auto-rename)
            final_path = target_path / original_name
            counter = 1
            while final_path.exists():
                stem = Path(original_name).stem
                suffix = Path(original_name).suffix
                final_path = target_path / f"{stem}_{counter}{suffix}"
                counter += 1

            # Move file from temp to session (efficient, no copy)
            shutil.move(str(temp_file), str(final_path))

            file_size = final_path.stat().st_size
            relative_path = str(final_path.relative_to(session_dir))

            committed.append(CommittedFileInfo(
                name=final_path.name,
                path=relative_path,
                size=file_size,
                type=mimetypes.guess_type(final_path.name)[0] or "application/octet-stream"
            ))

            logger.info(f"Committed file: {temp_file} → {final_path}")

        except Exception as e:
            logger.error(f"Failed to commit {file_id}: {e}")
            errors.append(FileUploadError(
                name=file_id,
                error=str(e)
            ))

    return FileCommitResponse(committed=committed, errors=errors)


@router.delete("/{session_id}/files/prepare")
async def cancel_file_preparation(
    session_id: str,
    file_ids: List[str] = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel prepared files (delete from temp storage).

    Use when user removes attachments before sending the message.

    Query parameters:
    - file_ids: List of temp file IDs to delete (e.g., ?file_ids=temp_abc_data.json&file_ids=temp_def_config.yaml)

    Returns list of deleted file IDs and any errors.
    """
    # Verify session exists
    service = AgentService(db)
    agent = await service.get_agent(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    session_temp_dir = TEMP_UPLOAD_DIR / session_id

    deleted = []
    errors = []

    for file_id in file_ids:
        try:
            # Security: Ensure file_id doesn't contain path traversal
            if ".." in file_id or "/" in file_id or "\\" in file_id:
                errors.append(FileUploadError(
                    name=file_id,
                    error="Invalid file ID"
                ))
                continue

            temp_file = session_temp_dir / file_id

            if temp_file.exists():
                temp_file.unlink()
                deleted.append(file_id)
                logger.info(f"Deleted temp file: {temp_file}")
            else:
                errors.append(FileUploadError(
                    name=file_id,
                    error="File not found"
                ))

        except Exception as e:
            logger.error(f"Failed to delete {file_id}: {e}")
            errors.append(FileUploadError(
                name=file_id,
                error=str(e)
            ))

    return {"deleted": deleted, "errors": errors}
