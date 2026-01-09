"""
Centralized character data loading and management.

This service provides a single point for loading character metadata,
creating symlinks, and caching character data.
"""

import asyncio
import logging
import os
import time
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class CharacterLoader:
    """
    Singleton service for character data management.

    Responsibilities:
    - Load character metadata from agent.md files
    - Create symlinks to character directories
    - Cache loaded characters to avoid repeated file reads
    - Provide access to character capabilities
    """

    _instance: Optional["CharacterLoader"] = None

    def __init__(self):
        """Initialize service with empty cache."""
        self._character_cache: Dict[str, any] = {}

    @classmethod
    def get_instance(cls) -> "CharacterLoader":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = CharacterLoader()
            logger.info("[CHAR_LOADER] Initialized CharacterLoader singleton")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (useful for testing)."""
        cls._instance = None

    async def load_character(self, character_id: str):
        """
        Load character from agent.md file with caching.

        Args:
            character_id: Character identifier (directory name in ~/.kumiai/agents/)

        Returns:
            Character object with metadata and content

        Raises:
            ValueError: If character not found
        """
        if character_id not in self._character_cache:
            from backend.utils.character_file import load_character_from_file

            start_time = time.time()
            logger.info(f"[CHAR_LOADER] Loading character '{character_id}' from file")

            character = await load_character_from_file(character_id)
            if character is None:
                raise ValueError(
                    f"Character '{character_id}' not found in ~/.kumiai/agents/"
                )

            self._character_cache[character_id] = character

            duration = time.time() - start_time
            logger.info(
                f"[CHAR_LOADER] ✓ Loaded character '{character.name}' in {duration:.3f}s "
                f"(color: {character.color}, avatar: {character.avatar or character_id})"
            )
        else:
            logger.debug(f"[CHAR_LOADER] Using cached character '{character_id}'")

        return self._character_cache[character_id]

    async def create_symlink(
        self,
        character_id: str,
        target_dir: Path,
        symlink_name: Optional[str] = None,
        source_base: Optional[Path] = None
    ):
        """
        Create symlink to character/skill directory in project/session directory.

        This makes the entire character folder (with all files/subdirs) available
        to Claude during session execution.

        Args:
            character_id: Character identifier (or skill_id when source_base is skills_dir)
            target_dir: Directory where symlink should be created (e.g., project/agents/)
            symlink_name: Optional name for symlink (defaults to character_id)
            source_base: Optional base directory (defaults to characters_dir, can be skills_dir)

        Returns:
            Path to created symlink
        """
        from backend.core.config import settings

        # Use provided source_base or default to characters_dir
        base_dir = source_base if source_base is not None else settings.characters_dir
        char_dir = base_dir / character_id
        symlink_name = symlink_name or character_id

        # Ensure target directory exists (run in executor to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: target_dir.mkdir(parents=True, exist_ok=True))

        agent_link = target_dir / symlink_name

        if not agent_link.exists():
            try:
                # Run symlink creation in executor to avoid blocking event loop
                await loop.run_in_executor(None, os.symlink, char_dir, agent_link, True)
                logger.info(
                    f"[CHAR_LOADER] ✓ Created symlink: {agent_link} -> {char_dir}"
                )
                logger.info(
                    f"[CHAR_LOADER] Character folder now available at {target_dir.name}/{symlink_name}/"
                )
            except FileExistsError:
                # Race condition - another process created it
                logger.debug(
                    f"[CHAR_LOADER] Symlink already exists (race condition): {agent_link}"
                )
            except Exception as e:
                logger.error(
                    f"[CHAR_LOADER] ✗ Failed to create symlink for {character_id}: {e}"
                )
                import traceback
                logger.debug(f"[CHAR_LOADER] Traceback: {traceback.format_exc()}")
        else:
            logger.debug(f"[CHAR_LOADER] Symlink already exists: {agent_link}")

        return agent_link

    async def load_capabilities(self, character_id: str, db):
        """
        Load capabilities for a character from database.

        Args:
            character_id: Character identifier
            db: Database session

        Returns:
            Capabilities object with allowed_tools, allowed_mcp_servers, etc.
        """
        from backend.models.database import Character
        from sqlalchemy import select

        # Load capabilities from database (not from file!)
        result = await db.execute(
            select(Character).where(Character.id == character_id)
        )
        db_char = result.scalar_one_or_none()

        if db_char:
            from backend.models.schemas import CharacterCapabilities
            return CharacterCapabilities(
                allowed_tools=db_char.allowed_tools or [],
                allowed_mcp_servers=db_char.allowed_mcp_servers or [],
                allowed_skills=db_char.allowed_skills or [],
            )
        else:
            # Return empty capabilities if no database record
            from backend.models.schemas import CharacterCapabilities
            return CharacterCapabilities(
                allowed_tools=[],
                allowed_mcp_servers=[],
                allowed_skills=[],
            )

    async def get_character_metadata(self, character_id: str) -> Dict[str, any]:
        """
        Get character metadata (name, color, avatar) without full load.

        Args:
            character_id: Character identifier

        Returns:
            Dict with name, color, avatar, description
        """
        character = await self.load_character(character_id)
        return {
            "name": character.name,
            "color": character.color,
            "avatar": character.avatar or character_id,
            "description": getattr(character, "description", ""),
        }

    def clear_cache(self):
        """Clear character cache (useful for development when editing agent.md files)."""
        self._character_cache.clear()
        logger.info("[CHAR_LOADER] Cleared character cache")
