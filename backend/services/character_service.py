"""Character management service."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid

from ..models.database import Character
from ..models.schemas import (
    CharacterDefinition,
    CharacterMetadata,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)


class CharacterService:
    """Service for managing characters."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_characters(self) -> list[CharacterMetadata]:
        """Get all character metadata by scanning filesystem and merging with database."""
        from ..core.config import settings
        from ..utils.character_file import CharacterFile

        characters_metadata = []

        # Ensure characters directory exists
        settings.characters_dir.mkdir(parents=True, exist_ok=True)

        # Load all database records (avatar + capabilities)
        result = await self.db.execute(select(Character))
        db_characters = {char.id: char for char in result.scalars().all()}

        # Scan character_library for character directories
        for char_dir in settings.characters_dir.iterdir():
            if not char_dir.is_dir():
                continue

            # Skip template directory
            if char_dir.name.startswith('_'):
                continue

            char_file_path = char_dir / "agent.md"
            if not char_file_path.exists():
                continue

            try:
                char_file = await CharacterFile.from_file(char_file_path)
                db_char = db_characters.get(char_dir.name)

                # Get avatar from database if available, otherwise from file
                avatar = db_char.avatar if db_char else char_file.avatar

                # Get skills from database (not from file!)
                skills = db_char.allowed_skills if db_char else []

                characters_metadata.append(
                    CharacterMetadata(
                        id=char_dir.name,
                        name=char_file.name,
                        avatar=avatar,
                        description=char_file.description,
                        color=char_file.color,
                        skills=skills,
                    )
                )
            except Exception as e:
                print(f"Error loading character {char_dir.name}: {e}")
                continue

        return characters_metadata

    async def get_character(self, character_id: str) -> Optional[CharacterDefinition]:
        """Get full character definition from filesystem + database (hybrid)."""
        from ..core.config import settings
        from ..utils.character_file import CharacterFile
        from ..models.schemas import CharacterCapabilities

        char_file_path = settings.characters_dir / character_id / "agent.md"

        if not char_file_path.exists():
            return None

        try:
            # Load content from FILE
            char_file = await CharacterFile.from_file(char_file_path)

            # Load capabilities from DATABASE
            result = await self.db.execute(
                select(Character).where(Character.id == character_id)
            )
            db_char = result.scalar_one_or_none()

            # Get avatar and capabilities from database
            avatar = db_char.avatar if db_char else char_file.avatar
            capabilities = None
            skills = []

            if db_char:
                capabilities = CharacterCapabilities(
                    allowed_tools=db_char.allowed_tools or [],
                    allowed_mcp_servers=db_char.allowed_mcp_servers or [],
                    allowed_skills=db_char.allowed_skills or [],
                )
                skills = db_char.allowed_skills or []

            return CharacterDefinition(
                id=character_id,
                name=char_file.name,
                avatar=avatar,
                description=char_file.description,
                color=char_file.color,
                skills=skills,
                default_model=char_file.default_model,
                personality=char_file.personality,
                capabilities=capabilities,
            )
        except Exception as e:
            print(f"Error loading character {character_id}: {e}")
            return None

    async def create_character(
        self, request: CreateCharacterRequest
    ) -> CharacterDefinition:
        """Create a new character by writing agent.md file and storing capabilities in database."""
        from ..core.config import settings
        from ..utils.character_file import CharacterFile
        from ..utils.slug import generate_unique_id

        # Generate human-readable ID if not provided
        if request.id:
            character_id = request.id
        else:
            # Generate slug from name (e.g., "Market Researcher" -> "market-researcher-a4b2")
            character_id = generate_unique_id(request.name, suffix_length=4)

        # Handle deprecated 'skills' field
        capabilities = request.capabilities
        if capabilities is None and request.skills:
            from ..models.schemas import CharacterCapabilities
            capabilities = CharacterCapabilities(allowed_skills=request.skills)

        # Create character directory
        char_dir = settings.characters_dir / character_id
        char_dir.mkdir(parents=True, exist_ok=True)

        # Build markdown content
        content = f"# {request.name}\n\n{request.description or ''}\n"
        if request.personality:
            content += f"\n## Personality\n\n{request.personality}\n"

        # Create character file (WITHOUT capabilities - they go to database)
        char_file = CharacterFile(
            name=request.name,
            description=request.description or "",
            content=content,
            avatar=request.avatar,
            color=request.color,
            default_model=request.default_model or "sonnet",
            personality=request.personality,
        )
        char_file.to_file(char_dir / "agent.md")

        # Store avatar + capabilities in DATABASE
        char = Character(
            id=character_id,
            avatar=request.avatar,
            allowed_tools=capabilities.allowed_tools if capabilities else [],
            allowed_mcp_servers=capabilities.allowed_mcp_servers if capabilities else [],
            allowed_skills=capabilities.allowed_skills if capabilities else [],
        )
        self.db.add(char)
        await self.db.flush()

        # Sync skill symlinks
        allowed_skills = capabilities.allowed_skills if capabilities else []
        self._sync_skill_symlinks(char_dir, allowed_skills)

        return CharacterDefinition(
            id=character_id,
            name=request.name,
            avatar=request.avatar,
            description=request.description,
            color=request.color,
            skills=allowed_skills,
            default_model=request.default_model or "sonnet",
            personality=request.personality,
            capabilities=capabilities,
        )

    async def update_character(
        self, character_id: str, request: UpdateCharacterRequest
    ) -> Optional[CharacterDefinition]:
        """Update an existing character by modifying agent.md file and database."""
        from ..core.config import settings
        from ..utils.character_file import CharacterFile

        char_file_path = settings.characters_dir / character_id / "agent.md"
        if not char_file_path.exists():
            return None

        # Read current file
        char_file = await CharacterFile.from_file(char_file_path)

        # Update FILE fields (free-form content)
        if request.name is not None:
            char_file.name = request.name
        if request.description is not None:
            char_file.description = request.description
        if request.color is not None:
            char_file.color = request.color
        if request.default_model is not None:
            char_file.default_model = request.default_model
        if request.personality is not None:
            char_file.personality = request.personality

        # Note: Do NOT rebuild content - preserve existing markdown body
        # The CharacterFile.to_file() will handle updating frontmatter and header
        # while preserving any custom sections the user has added

        # Write back to file
        char_file.to_file(char_file_path)

        # Update DATABASE fields (avatar + capabilities)
        result = await self.db.execute(
            select(Character).where(Character.id == character_id)
        )
        db_char = result.scalar_one_or_none()

        # Create database record if it doesn't exist
        if not db_char:
            db_char = Character(
                id=character_id,
                avatar=request.avatar,
                allowed_tools=[],
                allowed_mcp_servers=[],
                allowed_skills=[],
            )
            self.db.add(db_char)

        # Update avatar if provided
        if request.avatar is not None:
            db_char.avatar = request.avatar

        # Update capabilities if provided
        if request.capabilities is not None:
            db_char.allowed_tools = request.capabilities.allowed_tools
            db_char.allowed_mcp_servers = request.capabilities.allowed_mcp_servers
            db_char.allowed_skills = request.capabilities.allowed_skills
        elif request.skills is not None:
            # Handle deprecated 'skills' field
            db_char.allowed_skills = request.skills

        await self.db.flush()

        # Sync skill symlinks if capabilities changed
        if request.capabilities is not None or request.skills is not None:
            char_dir = settings.characters_dir / character_id
            allowed_skills = db_char.allowed_skills or []
            self._sync_skill_symlinks(char_dir, allowed_skills)

        # Build capabilities from database
        from ..models.schemas import CharacterCapabilities
        capabilities = CharacterCapabilities(
            allowed_tools=db_char.allowed_tools or [],
            allowed_mcp_servers=db_char.allowed_mcp_servers or [],
            allowed_skills=db_char.allowed_skills or [],
        )

        return CharacterDefinition(
            id=character_id,
            name=char_file.name,
            avatar=db_char.avatar,
            description=char_file.description,
            color=char_file.color,
            skills=db_char.allowed_skills or [],
            default_model=char_file.default_model,
            personality=char_file.personality,
            capabilities=capabilities,
        )

    async def delete_character(self, character_id: str) -> bool:
        """Delete a character (removes directory and database record)."""
        from ..core.config import settings
        import shutil

        char_dir = settings.characters_dir / character_id

        # Remove directory if it exists
        if char_dir.exists():
            shutil.rmtree(char_dir)

        # Remove database record (avatar seed) if it exists
        result = await self.db.execute(
            select(Character).where(Character.id == character_id)
        )
        char = result.scalar_one_or_none()

        if char:
            await self.db.delete(char)
            await self.db.flush()

        return True

    async def sync_character_from_filesystem(self, character_id: str) -> bool:
        """Sync skill symlinks and optionally create database record for avatar.

        This method is called after manual file edits to:
        1. Ensure skill symlinks are up to date (from database)
        2. Create database record if avatar is specified in file
        """
        from ..utils.character_file import CharacterFile
        from ..core.config import settings

        character_file_path = settings.characters_dir / character_id / "agent.md"

        if not character_file_path.exists():
            return False

        try:
            # Read from filesystem
            character_file = await CharacterFile.from_file(character_file_path)

            # Check if database record exists
            result = await self.db.execute(
                select(Character).where(Character.id == character_id)
            )
            db_character = result.scalar_one_or_none()

            # Only update/create database record if avatar is explicitly set in file
            if character_file.avatar is not None:
                if db_character:
                    db_character.avatar = character_file.avatar
                else:
                    db_character = Character(
                        id=character_id,
                        avatar=character_file.avatar,
                        allowed_tools=[],
                        allowed_mcp_servers=[],
                        allowed_skills=[],
                    )
                    self.db.add(db_character)
                await self.db.flush()

            # Sync skill symlinks (from database, not file)
            if db_character:
                char_dir = settings.characters_dir / character_id
                allowed_skills = db_character.allowed_skills or []
                self._sync_skill_symlinks(char_dir, allowed_skills)

            return True
        except Exception as e:
            print(f"Error syncing character {character_id}: {e}")
            return False

    def _sync_skill_symlinks(self, char_dir, allowed_skills: list[str]):
        """Sync skill directory symlinks with current skill list."""
        from pathlib import Path
        from ..core.config import settings
        import os

        # Remove old skill symlinks (not directories named 'skills' or 'resources')
        for item in char_dir.iterdir():
            if item.is_symlink() and item.is_dir():
                # Remove symlink
                item.unlink()

        # Create symlinks to skill directories
        for skill_id in allowed_skills:
            skill_source = settings.skills_dir / skill_id
            skill_link = char_dir / skill_id

            # Only create symlink if source exists
            if skill_source.exists() and skill_source.is_dir():
                # Create relative symlink
                try:
                    # Calculate relative path from char_dir to skill_source
                    relative_path = os.path.relpath(skill_source, char_dir)
                    skill_link.symlink_to(relative_path)
                except Exception as e:
                    print(f"Failed to create symlink for {skill_id}: {e}")

    async def get_character_files(self, character_id: str) -> Optional[list[dict]]:
        """Get file tree for a character directory."""
        from pathlib import Path
        from ..core.config import settings
        from ..utils.character_file import CharacterFile
        import json
        import shutil

        # Characters are stored in character_library directory
        char_dir = settings.characters_dir / character_id

        # Check if character exists by checking for agent.md file
        char_file_path = char_dir / "agent.md"
        if not char_file_path.exists():
            return None

        # Create directory if it doesn't exist
        if not char_dir.exists():
            char_dir.mkdir(parents=True, exist_ok=True)

        # Get skills from database
        try:
            result = await self.db.execute(
                select(Character).where(Character.id == character_id)
            )
            db_char = result.scalar_one_or_none()
            allowed_skills = db_char.allowed_skills if db_char else []
        except Exception:
            allowed_skills = []

        # Sync skill symlinks
        self._sync_skill_symlinks(char_dir, allowed_skills)

        def build_tree(path: Path, relative_to: Path) -> list[dict]:
            """Recursively build file tree."""
            items = []

            for item in sorted(path.iterdir(), key=lambda p: (not p.is_file(), p.name)):
                relative_path = str(item.relative_to(relative_to))

                if item.is_file():
                    items.append({
                        "name": item.name,
                        "path": relative_path,
                        "type": "file",
                        "size": item.stat().st_size,
                    })
                elif item.is_dir():
                    items.append({
                        "name": item.name,
                        "path": relative_path,
                        "type": "directory",
                        "children": build_tree(item, relative_to),
                    })

            return items

        return build_tree(char_dir, char_dir)

    async def get_character_file_content(
        self, character_id: str, file_path: str
    ) -> Optional[str]:
        """Get content of a specific file in character directory."""
        from pathlib import Path
        from ..core.config import settings

        char_dir = settings.characters_dir / character_id
        target_file = char_dir / file_path

        # Security check: ensure file is within character directory
        try:
            target_file.resolve().relative_to(char_dir.resolve())
        except ValueError:
            return None  # Path traversal attempt

        if not target_file.exists() or not target_file.is_file():
            return None

        try:
            return target_file.read_text()
        except Exception:
            return None

    async def update_character_file_content(
        self, character_id: str, file_path: str, content: str
    ) -> bool:
        """Update content of a specific file in character directory."""
        from pathlib import Path
        from ..core.config import settings

        char_dir = settings.characters_dir / character_id
        target_file = char_dir / file_path

        if not char_dir.exists():
            return False

        # Security check: ensure file is within character directory
        try:
            target_file.resolve().relative_to(char_dir.resolve())
        except ValueError:
            return False  # Path traversal attempt

        try:
            # Create parent directories if needed
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content)

            # If updating agent.md, also sync to database
            if file_path == "agent.md":
                await self.sync_character_from_filesystem(character_id)

            return True
        except Exception:
            return False

    async def delete_character_file(
        self, character_id: str, file_path: str
    ) -> bool:
        """Delete a specific file in character directory."""
        from pathlib import Path
        from ..core.config import settings
        import shutil

        char_dir = settings.characters_dir / character_id
        target_file = char_dir / file_path

        if not char_dir.exists():
            return False

        # Don't allow deleting agent.md
        if file_path == "agent.md":
            return False

        # Don't allow deleting skill directories/files
        result = await self.db.execute(
            select(Character).where(Character.id == character_id)
        )
        char = result.scalar_one_or_none()

        if char and char.allowed_skills:
            skill_ids = char.allowed_skills
            for skill_id in skill_ids:
                if file_path == skill_id or file_path.startswith(f"{skill_id}/"):
                    return False  # Don't delete skill directories or files

        # Security check: ensure file is within character directory
        try:
            target_file.resolve().relative_to(char_dir.resolve())
        except ValueError:
            return False  # Path traversal attempt

        if not target_file.exists():
            return False

        try:
            if target_file.is_file():
                target_file.unlink()
            elif target_file.is_dir():
                shutil.rmtree(target_file)
            return True
        except Exception:
            return False

    async def rename_character_file(
        self, character_id: str, old_path: str, new_path: str
    ) -> bool:
        """Rename a file in character directory."""
        from pathlib import Path
        from ..core.config import settings

        char_dir = settings.characters_dir / character_id
        old_file = char_dir / old_path
        new_file = char_dir / new_path

        if not char_dir.exists():
            return False

        # Don't allow renaming agent.md
        if old_path == "agent.md":
            return False

        # Don't allow renaming skill directories/files
        result = await self.db.execute(
            select(Character).where(Character.id == character_id)
        )
        char = result.scalar_one_or_none()

        if char and char.allowed_skills:
            skill_ids = char.allowed_skills
            for skill_id in skill_ids:
                if old_path == skill_id or old_path.startswith(f"{skill_id}/"):
                    return False  # Don't rename skill directories or files

        # Security check: ensure both paths are within character directory
        try:
            old_file.resolve().relative_to(char_dir.resolve())
            new_file.resolve().relative_to(char_dir.resolve())
        except ValueError:
            return False  # Path traversal attempt

        if not old_file.exists():
            return False

        if new_file.exists():
            return False  # Target already exists

        try:
            # Create parent directories if needed
            new_file.parent.mkdir(parents=True, exist_ok=True)
            old_file.rename(new_file)
            return True
        except Exception:
            return False
