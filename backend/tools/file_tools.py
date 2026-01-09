"""
File Tools

Provides agents with tools to display files to users.
"""

import json
import mimetypes
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool


def find_project_root(file_path: Path) -> Path | None:
    """
    Find project root by searching for .sessions or .git directory.

    Args:
        file_path: Starting path to search from

    Returns:
        Project root path if found, None otherwise
    """
    current = file_path if file_path.is_dir() else file_path.parent

    # Search up to 10 levels
    for _ in range(10):
        if (current / ".sessions").exists() or (current / ".git").exists():
            return current

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    return None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f}MB"


@tool(
    "show_file",
    "Display a file to the user. Shows an inline preview that they can click to view or download. "
    "Use this when you want to show the user a file you created or modified.",
    {
        "file_path": "Absolute path to the file in the project directory",
        "caption": "Optional caption or description for the file (e.g., 'Here is the analysis report I generated')"
    }
)
async def show_file(args: dict[str, Any]) -> dict[str, Any]:
    """
    Display a file to the user with an inline clickable preview.

    Args:
        args: Dictionary with:
            - file_path: Absolute path to file in project directory
            - caption: Optional caption/description

    Returns:
        Tool result with markdown text containing embedded file metadata
    """
    file_path_str = args.get("file_path", "")
    caption = args.get("caption", "")

    if not file_path_str:
        return {
            "content": [{
                "type": "text",
                "text": "❌ Error: file_path is required"
            }],
            "isError": True
        }

    file_path = Path(file_path_str).resolve()

    # Validate file exists
    if not file_path.exists():
        return {
            "content": [{
                "type": "text",
                "text": f"❌ Error: File not found: {file_path_str}"
            }],
            "isError": True
        }

    if not file_path.is_file():
        return {
            "content": [{
                "type": "text",
                "text": f"❌ Error: Path is not a file: {file_path_str}"
            }],
            "isError": True
        }

    # Find project root and convert to relative path
    project_root = find_project_root(file_path)

    if project_root:
        try:
            relative_path = file_path.relative_to(project_root)
            relative_path_str = str(relative_path)
        except ValueError:
            # File is outside project root
            relative_path_str = str(file_path)
    else:
        # Could not find project root, use absolute path
        relative_path_str = str(file_path)

    # Get file metadata
    file_name = file_path.name
    file_size = file_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "application/octet-stream"

    # Build metadata for frontend
    metadata = {
        "file_name": file_name,
        "file_path": relative_path_str,
        "file_size": file_size,
        "file_type": mime_type
    }

    # Create natural markdown with embedded metadata
    result_text = ""

    if caption:
        result_text = f"{caption}\n\n"    

    return {
        "content": [{
            "type": "text",
            "text": result_text
        }]
    }
