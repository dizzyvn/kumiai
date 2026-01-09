"""Skill API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.skill_service import SkillService
from ..models.schemas import (
    SkillDefinition,
    SkillMetadata,
    CreateSkillRequest,
    UpdateSkillRequest,
    SkillSearchResponse,
    ImportSkillRequest,
    ImportSkillResponse,
)

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillMetadata])
async def list_skills(db: AsyncSession = Depends(get_db)):
    """Get all skills."""
    service = SkillService(db)
    return await service.list_skills()


@router.get("/search", response_model=SkillSearchResponse)
async def search_skills(q: str, db: AsyncSession = Depends(get_db)):
    """
    Search skills with partial matching.

    Query parameter:
    - q: Search query string (searches name, description, and ID)

    Returns ranked results with match scores.
    """
    service = SkillService(db)
    return await service.search_skills(q)


@router.get("/{skill_id}", response_model=SkillDefinition)
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    """Get full skill definition."""
    service = SkillService(db)
    skill = await service.get_skill(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return skill


@router.post("", response_model=SkillDefinition, status_code=201)
async def create_skill(
    request: CreateSkillRequest, db: AsyncSession = Depends(get_db)
):
    """Create a new skill."""
    service = SkillService(db)
    return await service.create_skill(request)


@router.post("/import", response_model=ImportSkillResponse, status_code=201)
async def import_skill(
    request: ImportSkillRequest, db: AsyncSession = Depends(get_db)
):
    """
    Import a skill from GitHub URL or local directory.

    Supports:
    - GitHub URLs: https://github.com/user/repo/tree/branch/.claude/skills/skill-name
    - Local paths: /path/to/skill/directory

    The source directory must contain a SKILL.md file.
    """
    service = SkillService(db)
    try:
        skill, message = await service.import_skill(request.source, request.skill_id)
        return ImportSkillResponse(skill=skill, message=message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{skill_id}", response_model=SkillDefinition)
async def update_skill(
    skill_id: str,
    request: UpdateSkillRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing skill."""
    service = SkillService(db)
    skill = await service.update_skill(skill_id, request)

    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return skill


@router.post("/{skill_id}/sync", status_code=200)
async def sync_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    """Sync database from filesystem (after agent edits)."""
    service = SkillService(db)
    success = await service.sync_skill_from_filesystem(skill_id)

    if not success:
        raise HTTPException(status_code=404, detail="Skill not found or sync failed")

    return {"status": "synced"}


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a skill."""
    service = SkillService(db)
    deleted = await service.delete_skill(skill_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found")


@router.get("/tools/custom")
async def list_custom_tools():
    """Get all available custom tools from registered providers."""
    from ..services.claude_client import get_provider_manager
    from ..tools.provider_base import ToolContext

    # Get provider manager
    manager = await get_provider_manager()

    # Create context for listing tools (no specific character/project)
    context = ToolContext()

    # Get all tools from all providers
    all_tools = await manager.get_all_tools(context)

    # Filter to only custom tools (exclude MCP tools)
    custom_tools = [
        {
            "id": tool.tool_id,
            "provider": tool.provider,
            "category": tool.category,
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in all_tools
        if tool.provider in ["python", "http"]  # Only python__ and http__ tools
    ]

    return custom_tools


@router.get("/{skill_id}/files")
async def get_skill_files(skill_id: str, db: AsyncSession = Depends(get_db)):
    """Get file tree for a skill directory."""
    service = SkillService(db)
    files = await service.get_skill_files(skill_id)

    if files is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    return files


@router.get("/{skill_id}/files/content")
async def get_skill_file_content(
    skill_id: str,
    file_path: str,
    db: AsyncSession = Depends(get_db)
):
    """Get content of a specific file in skill directory."""
    service = SkillService(db)
    content = await service.get_skill_file_content(skill_id, file_path)

    if content is None:
        raise HTTPException(status_code=404, detail="File not found")

    return {"content": content, "path": file_path}


@router.put("/{skill_id}/files/content")
async def update_skill_file_content(
    skill_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """Update content of a specific file in skill directory."""
    file_path = request.get("file_path")
    content = request.get("content")

    if not file_path or content is None:
        raise HTTPException(status_code=400, detail="file_path and content required")

    service = SkillService(db)
    success = await service.update_skill_file_content(skill_id, file_path, content)

    if not success:
        raise HTTPException(status_code=404, detail="Skill or file not found")

    return {"status": "updated", "path": file_path}


@router.delete("/{skill_id}/files")
async def delete_skill_file(
    skill_id: str,
    file_path: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a file in skill directory."""
    service = SkillService(db)
    success = await service.delete_skill_file(skill_id, file_path)

    if not success:
        raise HTTPException(status_code=404, detail="File not found or cannot be deleted")

    return {"status": "deleted", "path": file_path}


@router.patch("/{skill_id}/files/rename")
async def rename_skill_file(
    skill_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """Rename a file in skill directory."""
    old_path = request.get("old_path")
    new_path = request.get("new_path")

    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="old_path and new_path required")

    service = SkillService(db)
    success = await service.rename_skill_file(skill_id, old_path, new_path)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="File not found, target exists, or cannot be renamed"
        )

    return {"status": "renamed", "old_path": old_path, "new_path": new_path}
