"""Bootstrap functionality for initializing KumiAI directories and templates."""
import shutil
from pathlib import Path
import logging

from backend.core.config import settings

logger = logging.getLogger(__name__)


def init_templates():
    """
    Initialize template directories in ~/.kumiai if they don't exist.

    Copies template files from backend/templates/ to ~/.kumiai/agents/_template/
    and ~/.kumiai/skills/_template/ on first run.
    """
    # Get template source directory (backend/templates)
    backend_dir = Path(__file__).parent.parent
    templates_source = backend_dir / "templates"

    if not templates_source.exists():
        logger.warning(f"Templates source directory not found: {templates_source}")
        return

    # Initialize agent templates
    agents_template_source = templates_source / "agents" / "_template"
    agents_template_dest = settings.agents_dir / "_template"

    if agents_template_source.exists() and not agents_template_dest.exists():
        try:
            logger.info(f"Creating agent templates at {agents_template_dest}")
            shutil.copytree(agents_template_source, agents_template_dest)
            logger.info("✓ Agent templates initialized")
        except Exception as e:
            logger.error(f"Failed to initialize agent templates: {e}")

    # Initialize skill templates
    skills_template_source = templates_source / "skills" / "_template"
    skills_template_dest = settings.skills_dir / "_template"

    if skills_template_source.exists() and not skills_template_dest.exists():
        try:
            logger.info(f"Creating skill templates at {skills_template_dest}")
            shutil.copytree(skills_template_source, skills_template_dest)
            logger.info("✓ Skill templates initialized")
        except Exception as e:
            logger.error(f"Failed to initialize skill templates: {e}")


def bootstrap():
    """
    Run all bootstrap initialization tasks.

    Called once during application startup to ensure all necessary
    directories and files are in place.
    """
    logger.info("Running KumiAI bootstrap...")

    # Ensure base directories exist
    settings.kumiai_home.mkdir(parents=True, exist_ok=True)
    settings.agents_dir.mkdir(parents=True, exist_ok=True)
    settings.skills_dir.mkdir(parents=True, exist_ok=True)
    settings.projects_dir.mkdir(parents=True, exist_ok=True)

    # Initialize templates
    init_templates()

    logger.info("✓ Bootstrap complete")
