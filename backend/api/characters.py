"""Character API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.character_service import CharacterService
from ..models.schemas import (
    CharacterDefinition,
    CharacterMetadata,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)

router = APIRouter(prefix="/characters", tags=["characters"])


@router.get("", response_model=list[CharacterMetadata])
async def list_characters(db: AsyncSession = Depends(get_db)):
    """Get all character templates."""
    service = CharacterService(db)
    return await service.list_characters()


# File-related routes must come BEFORE /{character_id} to avoid route conflicts
@router.get("/{character_id}/files")
async def get_character_files(character_id: str, db: AsyncSession = Depends(get_db)):
    """Get file tree for a character directory."""
    service = CharacterService(db)
    files = await service.get_character_files(character_id)

    if files is None:
        raise HTTPException(status_code=404, detail="Character not found")

    return files


@router.get("/{character_id}/files/content")
async def get_character_file_content(
    character_id: str,
    file_path: str,
    db: AsyncSession = Depends(get_db)
):
    """Get content of a specific file in character directory."""
    service = CharacterService(db)
    content = await service.get_character_file_content(character_id, file_path)

    if content is None:
        raise HTTPException(status_code=404, detail="File not found")

    return {"content": content, "path": file_path}


@router.put("/{character_id}/files/content")
async def update_character_file_content(
    character_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """Update content of a specific file in character directory."""
    file_path = request.get("file_path")
    content = request.get("content")

    if not file_path or content is None:
        raise HTTPException(status_code=400, detail="file_path and content required")

    service = CharacterService(db)
    success = await service.update_character_file_content(character_id, file_path, content)

    if not success:
        raise HTTPException(status_code=404, detail="Character or file not found")

    return {"status": "updated", "path": file_path}


@router.delete("/{character_id}/files")
async def delete_character_file(
    character_id: str,
    file_path: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a file in character directory."""
    service = CharacterService(db)
    success = await service.delete_character_file(character_id, file_path)

    if not success:
        raise HTTPException(status_code=404, detail="File not found or cannot be deleted")

    return {"status": "deleted", "path": file_path}


@router.patch("/{character_id}/files/rename")
async def rename_character_file(
    character_id: str,
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """Rename a file in character directory."""
    old_path = request.get("old_path")
    new_path = request.get("new_path")

    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="old_path and new_path required")

    service = CharacterService(db)
    success = await service.rename_character_file(character_id, old_path, new_path)

    if not success:
        raise HTTPException(status_code=404, detail="File not found or rename failed")

    return {"status": "renamed", "old_path": old_path, "new_path": new_path}


@router.get("/{character_id}", response_model=CharacterDefinition)
async def get_character(character_id: str, db: AsyncSession = Depends(get_db)):
    """Get full character definition."""
    service = CharacterService(db)
    character = await service.get_character(character_id)

    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    return character


@router.post("", response_model=CharacterDefinition, status_code=201)
async def create_character(
    request: CreateCharacterRequest, db: AsyncSession = Depends(get_db)
):
    """Create a new character."""
    service = CharacterService(db)
    return await service.create_character(request)


@router.put("/{character_id}", response_model=CharacterDefinition)
async def update_character(
    character_id: str,
    request: UpdateCharacterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing character."""
    service = CharacterService(db)
    character = await service.update_character(character_id, request)

    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    return character


@router.delete("/{character_id}", status_code=204)
async def delete_character(character_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a character."""
    service = CharacterService(db)
    deleted = await service.delete_character(character_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Character not found")


@router.post("/sync/{character_id}", status_code=200)
async def sync_character(character_id: str, db: AsyncSession = Depends(get_db)):
    """Sync database from filesystem (after agent edits)."""
    service = CharacterService(db)
    success = await service.sync_character_from_filesystem(character_id)

    if not success:
        raise HTTPException(
            status_code=404, detail="Character not found or sync failed"
        )

    return {"status": "synced"}
