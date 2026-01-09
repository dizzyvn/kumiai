"""Generate context files (PROJECT.md, SESSION.md) for agents."""
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def setup_session_directory_structure(session_path: Path) -> None:
    """
    Create standardized session directory structure.

    Structure:
    - agents/          # Agent configurations (symlinks)
    - working/         # Working files during execution
    - SESSION.md       # Session context and requirements

    Args:
        session_path: Path to session directory
    """
    session_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (session_path / "agents").mkdir(exist_ok=True)
    (session_path / "working").mkdir(exist_ok=True)

    logger.info(f"Session directory structure created at {session_path}")


async def generate_project_md(
    project_path: str,
    project_id: str,
    project_name: str,
    project_description: Optional[str],
    team_member_ids: Optional[list[str]],
    pm_character_id: Optional[str] = None,
) -> Path:
    """Generate PROJECT.md file with project metadata.

    Args:
        project_path: Path to project directory
        project_id: Project ID
        project_name: Project name
        project_description: Project description
        team_member_ids: List of team member character IDs
        pm_character_id: Optional PM character ID

    Returns:
        Path to created PROJECT.md file
    """
    from ..services.character_service import CharacterService
    from ..core.database import AsyncSessionLocal

    # Load team member and PM information
    team_members_info = []
    pm_info = None

    async with AsyncSessionLocal() as db:
        character_service = CharacterService(db)

        # Load PM character if specified
        if pm_character_id:
            try:
                pm_char = await character_service.get_character(pm_character_id)
                if pm_char:
                    pm_info = {
                        'name': pm_char.name,
                        'description': pm_char.description or 'No description',
                    }
            except Exception as e:
                logger.warning(f"Failed to load PM character {pm_character_id}: {e}")

        # Load team members
        if team_member_ids:
            for member_id in team_member_ids:
                try:
                    member = await character_service.get_character(member_id)
                    if member:
                        team_members_info.append({
                            'id': member_id,
                            'name': member.name,
                            'description': member.description or 'No description',
                        })
                except Exception as e:
                    logger.warning(f"Failed to load team member {member_id}: {e}")

    # Build PROJECT.md content
    content = f"""# {project_name}

**Project ID:** `{project_id}`
**Project Path:** `{project_path}`

## Description

{project_description or 'No description provided'}

"""

    # Add PM section if available
    if pm_info:
        content += f"""## Project Manager

**{pm_info['name']}**
{pm_info['description']}

"""

    # Add team members section
    if team_members_info:
        content += """## Team Members

"""
        for member in team_members_info:
            content += f"""### {member['name']} (`{member['id']}`)

{member['description']}

"""
    else:
        content += """## Team Members

No team members assigned yet.

"""

    # Create project directory if it doesn't exist
    project_dir = Path(project_path)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Write PROJECT.md
    project_md_path = project_dir / "PROJECT.md"
    project_md_path.write_text(content, encoding='utf-8')

    logger.info(f"Created PROJECT.md at {project_md_path}")
    return project_md_path


async def generate_session_md(
    session_path: str,
    instance_id: str,
    project_id: str,
    session_description: str,
    specialist_ids: list[str],
) -> Path:
    """Generate SESSION.md file with session metadata.

    Args:
        session_path: Path to session directory (e.g., {project}/.sessions/{instance_id})
        instance_id: Instance ID
        project_id: Project ID this session belongs to
        session_description: Description of what this session should accomplish
        specialist_ids: List of specialist character IDs assigned to this session

    Returns:
        Path to created SESSION.md file
    """
    from ..services.character_service import CharacterService
    from ..core.database import AsyncSessionLocal

    # Load specialist information
    specialists_info = []

    async with AsyncSessionLocal() as db:
        character_service = CharacterService(db)

        for specialist_id in specialist_ids:
            try:
                specialist = await character_service.get_character(specialist_id)
                if specialist:
                    specialists_info.append({
                        'id': specialist_id,
                        'name': specialist.name,
                        'description': specialist.description or 'No description',
                        'skills': specialist.capabilities.allowed_skills if specialist.capabilities else [],
                    })
            except Exception as e:
                logger.warning(f"Failed to load specialist {specialist_id}: {e}")

    # Build SESSION.md content
    content = f"""# Session: {session_description[:100]}{'...' if len(session_description) > 100 else ''}

**Instance ID:** `{instance_id}`
**Project ID:** `{project_id}`
**Session Path:** `{session_path}`

## Goal

{session_description}

## Team Specialists

"""

    if specialists_info:
        for specialist in specialists_info:
            skills_str = ", ".join(specialist['skills']) if specialist['skills'] else 'No skills assigned'
            content += f"""### {specialist['name']} (`{specialist['id']}`)

{specialist['description']}

**Skills:** {skills_str}

"""
    else:
        content += """No specialists assigned to this session.

"""

    # Create session directory if it doesn't exist
    session_dir = Path(session_path)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write SESSION.md
    session_md_path = session_dir / "SESSION.md"
    session_md_path.write_text(content, encoding='utf-8')

    logger.info(f"Created SESSION.md at {session_md_path}")
    return session_md_path
