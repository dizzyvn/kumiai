"""Character file management utilities."""
import asyncio
import re
from pathlib import Path
from typing import Optional
import yaml


class CharacterFile:
    """Represents a character file with YAML frontmatter and Markdown content.

    This class only handles FREE-FORM content from agent.md:
    - name, description, personality
    - system prompt content
    - custom instructions

    Capabilities (tools, MCP servers, skills) are stored in DATABASE, not here.
    """

    def __init__(
        self,
        name: str,
        description: str,
        content: str,
        avatar: Optional[str] = None,
        color: Optional[str] = None,
        default_model: Optional[str] = None,
        personality: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.content = content
        self.avatar = avatar  # Avatar seed for DiceBear (optional, defaults to name)
        self.color = color or "#4A90E2"
        self.default_model = default_model or "sonnet"
        self.personality = personality

        # NOTE: capabilities are NOT stored here - they're in the database
        # See Character model: allowed_tools, allowed_mcp_servers, allowed_skills

    @classmethod
    async def from_file(cls, file_path: Path, skills_dir: Optional[Path] = None) -> "CharacterFile":
        """Parse an AGENT.md file with YAML frontmatter.

        Only loads free-form content. Capabilities are in database.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Character file not found: {file_path}")

        # Read file asynchronously using executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, file_path.read_text)

        # Parse YAML frontmatter
        frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
        if not frontmatter_match:
            raise ValueError(f"Invalid character file format: {file_path}")

        frontmatter_text = frontmatter_match.group(1)
        markdown_content = frontmatter_match.group(2).strip()

        # Parse YAML (CPU-bound operation, run in executor)
        frontmatter = await loop.run_in_executor(None, yaml.safe_load, frontmatter_text)

        # Parse name from frontmatter or first h1 heading
        name = frontmatter.get("name")
        if not name:
            name_match = re.search(r"^#\s+(.+)$", markdown_content, re.MULTILINE)
            name = name_match.group(1) if name_match else "Unnamed Agent"

        # Parse description from frontmatter or first paragraph
        description = frontmatter.get("description", "")
        if not description:
            desc_match = re.search(r"^#\s+.+\n\n(.+?)(?:\n\n|\Z)", markdown_content, re.MULTILINE | re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""

        return cls(
            name=name,
            description=description,
            content=markdown_content,
            avatar=frontmatter.get("avatar"),
            color=frontmatter.get("color", "#4A90E2"),
            default_model=frontmatter.get("default_model", "sonnet"),
            personality=frontmatter.get("personality"),
        )

    async def to_file(self, file_path: Path) -> None:
        """Write character to AGENT.md file with YAML frontmatter.

        Only writes free-form content. Capabilities are in database.
        """
        # Ensure directory exists (run in executor to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: file_path.parent.mkdir(parents=True, exist_ok=True))

        # Build frontmatter (only metadata, no capabilities)
        frontmatter = {
            "name": self.name,
            "description": self.description,
        }

        # Optional fields
        if self.avatar:
            frontmatter["avatar"] = self.avatar
        if self.color != "#4A90E2":
            frontmatter["color"] = self.color
        if self.default_model != "sonnet":
            frontmatter["default_model"] = self.default_model
        if self.personality:
            frontmatter["personality"] = self.personality

        # Build file content (CPU-bound operation in executor)
        def build_content():
            frontmatter_yaml = yaml.dump(
                frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True
            )
            return f"---\n{frontmatter_yaml}---\n\n{self.content}"

        file_content = await loop.run_in_executor(None, build_content)

        # Write to file asynchronously
        await loop.run_in_executor(None, file_path.write_text, file_content, "utf-8")

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Only includes free-form content. Capabilities are in database.
        """
        return {
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "avatar": self.avatar,
            "color": self.color,
            "default_model": self.default_model,
            "personality": self.personality,
        }


async def load_character_from_file(character_id: str) -> Optional[CharacterFile]:
    """Load character data directly from ~/.kumiai/agents/{id}/agent.md file.

    Args:
        character_id: Character ID (directory name in ~/.kumiai/agents/)

    Returns:
        CharacterFile instance or None if file doesn't exist

    Raises:
        ValueError: If file exists but is malformed
    """
    from ..core.config import settings

    character_file_path = settings.characters_dir / character_id / "agent.md"

    if not character_file_path.exists():
        return None

    try:
        return await CharacterFile.from_file(character_file_path)
    except Exception as e:
        raise ValueError(f"Failed to parse character file for '{character_id}': {e}") from e
