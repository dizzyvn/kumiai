"""Skill file management utilities."""
import asyncio
import re
from pathlib import Path
from typing import Optional
import yaml


class SkillFile:
    """Represents a skill file with YAML frontmatter and Markdown content.

    Skills are PURE DOCUMENTATION - no tool/MCP server declarations.
    They describe workflows, patterns, and best practices.

    Tool and MCP server requirements are in Character database.
    """

    def __init__(
        self,
        name: str,
        description: str,
        content: str,
        license: Optional[str] = None,
        version: Optional[str] = None,
        icon: Optional[str] = None,
        icon_color: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.content = content
        self.license = license or "Apache-2.0"
        self.version = version or "1.0.0"
        self.icon = icon or "wrench"
        self.icon_color = icon_color or "#6b7280"

        # REMOVED: allowed_tools, allowed_mcp_servers, allowed_custom_tools
        # These are in Character database, not in skills

    @classmethod
    async def from_file(cls, file_path: Path) -> "SkillFile":
        """Parse a SKILL.md file with YAML frontmatter.

        Only loads documentation content. No tool/MCP declarations.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Skill file not found: {file_path}")

        # Read file asynchronously using executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, file_path.read_text)

        # Parse YAML frontmatter
        frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
        if not frontmatter_match:
            raise ValueError(f"Invalid skill file format: {file_path}")

        frontmatter_text = frontmatter_match.group(1)
        markdown_content = frontmatter_match.group(2).strip()

        # Parse YAML (CPU-bound operation, run in executor)
        frontmatter = await loop.run_in_executor(None, yaml.safe_load, frontmatter_text)

        return cls(
            name=frontmatter.get("name", ""),
            description=frontmatter.get("description", ""),
            content=markdown_content,
            license=frontmatter.get("license"),
            version=frontmatter.get("version"),
            icon=frontmatter.get("icon"),
            icon_color=frontmatter.get("iconColor"),
        )

    async def to_file(self, file_path: Path) -> None:
        """Write skill to SKILL.md file with YAML frontmatter.

        Only writes documentation content. No tool/MCP declarations.
        """
        # Ensure directory exists (run in executor to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: file_path.parent.mkdir(parents=True, exist_ok=True))

        # Build frontmatter (no tool/MCP declarations)
        frontmatter = {
            "name": self.name,
            "description": self.description,
            "license": self.license,
            "version": self.version,
        }

        # Optional fields
        if self.icon != "wrench":
            frontmatter["icon"] = self.icon
        if self.icon_color != "#6b7280":
            frontmatter["iconColor"] = self.icon_color

        # Build file content (CPU-bound operation in executor)
        def build_content():
            frontmatter_yaml = yaml.dump(
                frontmatter, default_flow_style=False, sort_keys=False
            )
            return f"---\n{frontmatter_yaml}---\n\n{self.content}"

        file_content = await loop.run_in_executor(None, build_content)

        # Write to file asynchronously
        await loop.run_in_executor(None, file_path.write_text, file_content)

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Only includes documentation content. No tool/MCP declarations.
        """
        return {
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "license": self.license,
            "version": self.version,
            "icon": self.icon,
            "iconColor": self.icon_color,
        }


async def load_skill_from_file(skill_id: str) -> Optional[SkillFile]:
    """Load skill data directly from ~/.kumiai/skills/{id}/skill.md file.

    Args:
        skill_id: Skill ID (directory name in ~/.kumiai/skills/)

    Returns:
        SkillFile instance or None if file doesn't exist

    Raises:
        ValueError: If file exists but is malformed
    """
    from ..core.config import settings

    skill_file_path = settings.skills_dir / skill_id / "SKILL.md"

    if not skill_file_path.exists():
        return None

    try:
        return await SkillFile.from_file(skill_file_path)
    except Exception as e:
        raise ValueError(f"Failed to parse skill file for '{skill_id}': {e}") from e
