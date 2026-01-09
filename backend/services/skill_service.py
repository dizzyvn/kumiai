"""Skill management service with file-only storage (pure documentation)."""
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pathlib import Path
import re
import urllib.request
import urllib.error
import shutil
import json

from ..core.config import settings
from ..models.schemas import (
    SkillDefinition,
    SkillMetadata,
    CreateSkillRequest,
    UpdateSkillRequest,
    SkillSearchResult,
    SkillSearchResponse,
)
from ..utils.skill_file import SkillFile


class SkillService:
    """Service for managing skills with file-based storage."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.skills_dir = settings.skills_dir

    async def list_skills(self) -> list[SkillMetadata]:
        """Get all skill metadata by scanning filesystem."""
        skills_metadata = []

        # Ensure skills directory exists
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # Scan skill_library for skill directories
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file_path = skill_dir / "skill.md"
            if not skill_file_path.exists():
                continue

            try:
                skill_file = await SkillFile.from_file(skill_file_path)

                # Check for scripts and resources directories
                has_scripts = (skill_dir / "scripts").exists() and (skill_dir / "scripts").is_dir()
                has_resources = (skill_dir / "resources").exists() and (skill_dir / "resources").is_dir()

                skills_metadata.append(
                    SkillMetadata(
                        id=skill_dir.name,
                        name=skill_file.name,
                        description=skill_file.description,
                        has_scripts=has_scripts,
                        has_resources=has_resources,
                        icon=skill_file.icon,
                        iconColor=skill_file.icon_color,
                    )
                )
            except Exception as e:
                print(f"Error loading skill {skill_dir.name}: {e}")
                continue

        return skills_metadata

    async def search_skills(self, query: str) -> SkillSearchResponse:
        """
        Search skills with partial matching and ranking.

        Scoring:
        - Exact match: 100
        - Starts with query: 90
        - Word boundary match: 80
        - Substring in name: 60
        - Substring in description: 40
        - Substring in ID: 30
        """
        if not query:
            return SkillSearchResponse(query=query, results=[])

        query_lower = query.lower()
        results = []

        # Get all skills
        all_skills = await self.list_skills()

        for skill in all_skills:
            name_lower = skill.name.lower()
            desc_lower = (skill.description or "").lower()
            id_lower = skill.id.lower()

            score = 0
            match_field = ""
            match_text = ""

            # Check name matches
            if name_lower == query_lower:
                score = 100
                match_field = "name"
                match_text = skill.name
            elif name_lower.startswith(query_lower):
                score = 90
                match_field = "name"
                match_text = skill.name
            elif any(word.startswith(query_lower) for word in name_lower.split()):
                score = 80
                match_field = "name"
                match_text = skill.name
            elif query_lower in name_lower:
                score = 60
                match_field = "name"
                match_text = skill.name

            # Check description matches (only if name didn't match)
            elif query_lower in desc_lower:
                score = 40
                match_field = "description"
                match_text = skill.description or ""

            # Check ID matches (only if name and description didn't match)
            elif query_lower in id_lower:
                score = 30
                match_field = "id"
                match_text = skill.id

            # Add to results if matched
            if score > 0:
                results.append(
                    SkillSearchResult(
                        skill=skill,
                        score=score,
                        match_field=match_field,
                        match_text=match_text,
                    )
                )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return SkillSearchResponse(query=query, results=results)

    async def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        """Get full skill definition from filesystem."""
        skill_file_path = self.skills_dir / skill_id / "skill.md"

        if not skill_file_path.exists():
            return None

        try:
            skill_file = await SkillFile.from_file(skill_file_path)
            return SkillDefinition(
                id=skill_id,
                name=skill_file.name,
                description=skill_file.description,
                content=skill_file.content,
                license=skill_file.license,
                version=skill_file.version,
                icon=skill_file.icon,
                iconColor=skill_file.icon_color,
            )
        except Exception as e:
            print(f"Error loading skill {skill_id}: {e}")
            return None

    async def sync_skill_from_filesystem(self, skill_id: str) -> bool:
        """Validate skill file exists (no database sync needed for skills)."""
        skill_file_path = self.skills_dir / skill_id / "skill.md"

        if not skill_file_path.exists():
            return False

        try:
            # Just validate the file can be parsed
            await SkillFile.from_file(skill_file_path)
            return True
        except Exception as e:
            print(f"Error validating skill {skill_id}: {e}")
            return False

    async def create_skill(self, request: CreateSkillRequest) -> SkillDefinition:
        """Create a new skill by writing to filesystem only (pure documentation)."""
        skill_id = request.id

        # Create skill file (pure documentation, no tool declarations)
        skill_file = SkillFile(
            name=request.name,
            description=request.description,
            content=request.content,
            license=request.license or "Apache-2.0",
            version=request.version or "1.0.0",
            icon=request.icon or "wrench",
            icon_color=request.iconColor or "#6b7280",
        )

        # Write to filesystem
        skill_file_path = self.skills_dir / skill_id / "skill.md"
        skill_file.to_file(skill_file_path)

        return SkillDefinition(
            id=skill_id,
            name=request.name,
            description=request.description,
            content=request.content,
            license=skill_file.license,
            version=skill_file.version,
            icon=request.icon or "wrench",
            iconColor=request.iconColor or "#6b7280",
        )

    async def update_skill(
        self, skill_id: str, request: UpdateSkillRequest
    ) -> Optional[SkillDefinition]:
        """Update an existing skill by modifying filesystem only (pure documentation)."""
        skill_file_path = self.skills_dir / skill_id / "skill.md"

        if not skill_file_path.exists():
            return None

        # Read existing skill
        skill_file = await SkillFile.from_file(skill_file_path)

        # Update fields
        if request.name is not None:
            skill_file.name = request.name
        if request.description is not None:
            skill_file.description = request.description
        if request.content is not None:
            skill_file.content = request.content
        if request.license is not None:
            skill_file.license = request.license
        if request.version is not None:
            skill_file.version = request.version
        if request.icon is not None:
            skill_file.icon = request.icon
        if request.iconColor is not None:
            skill_file.icon_color = request.iconColor

        # Write back to filesystem
        skill_file.to_file(skill_file_path)

        return SkillDefinition(
            id=skill_id,
            name=skill_file.name,
            description=skill_file.description,
            content=skill_file.content,
            license=skill_file.license,
            version=skill_file.version,
            icon=skill_file.icon,
            iconColor=skill_file.icon_color,
        )

    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill from filesystem only."""
        skill_dir = self.skills_dir / skill_id

        if not skill_dir.exists():
            return False

        # Delete from filesystem
        import shutil
        shutil.rmtree(skill_dir)

        return True

    async def get_skill_files(self, skill_id: str) -> Optional[list[dict]]:
        """Get file tree for a skill directory."""
        skill_dir = self.skills_dir / skill_id

        if not skill_dir.exists():
            return None

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

        return build_tree(skill_dir, skill_dir)

    async def get_skill_file_content(
        self, skill_id: str, file_path: str
    ) -> Optional[str]:
        """Get content of a specific file in skill directory."""
        skill_dir = self.skills_dir / skill_id
        target_file = skill_dir / file_path

        # Security check: ensure file is within skill directory
        try:
            target_file.resolve().relative_to(skill_dir.resolve())
        except ValueError:
            return None  # Path traversal attempt

        if not target_file.exists() or not target_file.is_file():
            return None

        try:
            return target_file.read_text()
        except Exception:
            return None

    async def update_skill_file_content(
        self, skill_id: str, file_path: str, content: str
    ) -> bool:
        """Update content of a specific file in skill directory."""
        skill_dir = self.skills_dir / skill_id
        target_file = skill_dir / file_path

        if not skill_dir.exists():
            return False

        # Security check: ensure file is within skill directory
        try:
            target_file.resolve().relative_to(skill_dir.resolve())
        except ValueError:
            return False  # Path traversal attempt

        try:
            # Create parent directories if needed
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content)
            return True
        except Exception:
            return False

    async def delete_skill_file(self, skill_id: str, file_path: str) -> bool:
        """Delete a specific file in skill directory."""
        skill_dir = self.skills_dir / skill_id
        target_file = skill_dir / file_path

        if not skill_dir.exists():
            return False

        # Don't allow deleting skill.md
        if file_path == "skill.md":
            return False

        # Security check: ensure file is within skill directory
        try:
            target_file.resolve().relative_to(skill_dir.resolve())
        except ValueError:
            return False  # Path traversal attempt

        if not target_file.exists():
            return False

        try:
            if target_file.is_file():
                target_file.unlink()
            elif target_file.is_dir():
                import shutil
                shutil.rmtree(target_file)
            return True
        except Exception:
            return False

    async def rename_skill_file(
        self, skill_id: str, old_path: str, new_path: str
    ) -> bool:
        """Rename a file in skill directory."""
        skill_dir = self.skills_dir / skill_id
        old_file = skill_dir / old_path
        new_file = skill_dir / new_path

        if not skill_dir.exists():
            return False

        # Don't allow renaming skill.md
        if old_path == "skill.md":
            return False

        # Security check: ensure both paths are within skill directory
        try:
            old_file.resolve().relative_to(skill_dir.resolve())
            new_file.resolve().relative_to(skill_dir.resolve())
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

    async def import_skill(
        self, source: str, skill_id: Optional[str] = None
    ) -> tuple[SkillDefinition, str]:
        """
        Import a skill from GitHub URL or local directory.

        Args:
            source: GitHub URL or local directory path
            skill_id: Optional custom skill ID (auto-generated if not provided)

        Returns:
            Tuple of (SkillDefinition, message)

        Raises:
            ValueError: If source is invalid or skill import fails
        """
        # Determine if source is GitHub URL or local path
        if source.startswith("http://") or source.startswith("https://"):
            return await self._import_from_github(source, skill_id)
        else:
            return await self._import_from_local(source, skill_id)

    async def _import_from_github(
        self, github_url: str, skill_id: Optional[str] = None
    ) -> tuple[SkillDefinition, str]:
        """Import skill from GitHub URL, fetching all files recursively."""
        # Parse GitHub URL to get API endpoint
        # Example: https://github.com/user/repo/tree/branch/.claude/skills/skill-name
        # Convert to: https://api.github.com/repos/user/repo/contents/.claude/skills/skill-name?ref=branch

        pattern = r"github\.com/([^/]+)/([^/]+)/(?:tree|blob)/([^/]+)/(.+)"
        match = re.search(pattern, github_url)

        if not match:
            raise ValueError("Invalid GitHub URL format")

        user, repo, branch, path = match.groups()

        # Remove .git suffix from repo if present
        repo = repo.replace(".git", "")

        # Construct API URL for directory contents
        api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}?ref={branch}"

        # Recursively fetch all files from GitHub
        def fetch_directory_recursive(api_path: str, target_dir: Path) -> None:
            """Recursively fetch all files from a GitHub directory."""
            try:
                request = urllib.request.Request(api_path)
                # Add User-Agent header (required by GitHub API)
                request.add_header('User-Agent', 'opcode-skill-importer')

                with urllib.request.urlopen(request) as response:
                    contents = json.loads(response.read().decode('utf-8'))
            except urllib.error.URLError as e:
                raise ValueError(f"Failed to fetch directory from GitHub: {e}")

            if not isinstance(contents, list):
                raise ValueError("Expected directory listing from GitHub API")

            for item in contents:
                item_name = item.get('name', '')
                item_type = item.get('type', '')
                item_path = item.get('path', '')

                if item_type == 'file':
                    # Download file content
                    download_url = item.get('download_url')
                    if not download_url:
                        continue

                    try:
                        with urllib.request.urlopen(download_url) as file_response:
                            file_content = file_response.read()

                        # Write file to target directory
                        target_file = target_dir / item_name
                        target_file.write_bytes(file_content)
                    except Exception as e:
                        print(f"Warning: Failed to download {item_name}: {e}")

                elif item_type == 'dir':
                    # Create subdirectory and recursively fetch its contents
                    subdir = target_dir / item_name
                    subdir.mkdir(parents=True, exist_ok=True)

                    # Fetch subdirectory contents
                    subdir_api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{item_path}?ref={branch}"
                    fetch_directory_recursive(subdir_api_url, subdir)

        # Generate skill ID if not provided
        if not skill_id:
            # Use last part of path as skill ID
            skill_id = path.split('/')[-1]
            # Sanitize skill ID
            skill_id = re.sub(r'[^a-z0-9-]', '-', skill_id.lower())

        # Check if skill already exists
        skill_dir = self.skills_dir / skill_id
        if skill_dir.exists():
            raise ValueError(f"Skill '{skill_id}' already exists")

        # Create skill directory
        skill_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Fetch all files recursively
            fetch_directory_recursive(api_url, skill_dir)
        except Exception as e:
            # Clean up on failure
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
            raise ValueError(f"Failed to import skill from GitHub: {e}")

        # Verify SKILL.md was downloaded
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            # Try lowercase skill.md
            skill_md_path = skill_dir / "skill.md"
            if not skill_md_path.exists():
                # Clean up and raise error
                shutil.rmtree(skill_dir)
                raise ValueError("SKILL.md not found in GitHub repository")

        # Parse skill metadata from SKILL.md
        try:
            skill_file = await SkillFile.from_file(skill_md_path)
        except Exception as e:
            # Clean up on failure
            shutil.rmtree(skill_dir)
            raise ValueError(f"Invalid SKILL.md format: {e}")

        # Return skill definition
        skill_def = SkillDefinition(
            id=skill_id,
            name=skill_file.name,
            description=skill_file.description,
            content=skill_file.content,
            license=skill_file.license,
            version=skill_file.version,
            icon=skill_file.icon,
            iconColor=skill_file.icon_color,
        )

        message = f"Successfully imported skill '{skill_file.name}' from GitHub (all files)"
        return skill_def, message

    async def _import_from_local(
        self, local_path: str, skill_id: Optional[str] = None
    ) -> tuple[SkillDefinition, str]:
        """Import skill from local directory."""
        source_dir = Path(local_path).resolve()

        if not source_dir.exists():
            raise ValueError(f"Source directory does not exist: {local_path}")

        if not source_dir.is_dir():
            raise ValueError(f"Source must be a directory: {local_path}")

        # Check for SKILL.md
        skill_md_path = source_dir / "SKILL.md"
        if not skill_md_path.exists():
            raise ValueError("SKILL.md not found in source directory")

        # Parse skill metadata
        try:
            skill_file = await SkillFile.from_file(skill_md_path)
        except Exception as e:
            raise ValueError(f"Invalid SKILL.md format: {e}")

        # Generate skill ID if not provided
        if not skill_id:
            skill_id = source_dir.name
            # Sanitize skill ID
            skill_id = re.sub(r'[^a-z0-9-]', '-', skill_id.lower())

        # Check if skill already exists
        skill_dir = self.skills_dir / skill_id
        if skill_dir.exists():
            raise ValueError(f"Skill '{skill_id}' already exists")

        # Copy entire directory
        try:
            shutil.copytree(source_dir, skill_dir)
        except Exception as e:
            raise ValueError(f"Failed to copy skill directory: {e}")

        # Return skill definition
        skill_def = SkillDefinition(
            id=skill_id,
            name=skill_file.name,
            description=skill_file.description,
            content=skill_file.content,
            license=skill_file.license,
            version=skill_file.version,
            icon=skill_file.icon,
            iconColor=skill_file.icon_color,
        )

        message = f"Successfully imported skill '{skill_file.name}' from local directory"
        return skill_def, message
