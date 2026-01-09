"""Application configuration."""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings."""

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 7892
    cors_origins: list[str] = [
        "http://localhost:1420",
        "http://localhost:5749",
        "http://localhost:5174",
        "http://localhost:5173",
        "*",  # Allow all origins for local network access
    ]

    # Paths
    base_dir: Path = Path(__file__).parent.parent.parent

    # KumiAI home directory (hardcoded to ~/.kumiai)
    @property
    def kumiai_home(self) -> Path:
        """Get KumiAI home directory path."""
        return Path.home() / ".kumiai"

    @property
    def characters_dir(self) -> Path:
        """Get characters directory path (hardcoded to ~/.kumiai/agents)."""
        return self.kumiai_home / "agents"

    @property
    def skills_dir(self) -> Path:
        """Get skills directory path (hardcoded to ~/.kumiai/skills)."""
        return self.kumiai_home / "skills"

    @property
    def projects_dir(self) -> Path:
        """Get projects directory path (hardcoded to ~/.kumiai/projects)."""
        return self.kumiai_home / "projects"

    # Legacy aliases (deprecated - use characters_dir and skills_dir instead)
    @property
    def agents_dir(self) -> Path:
        """Legacy alias for characters_dir."""
        return self.characters_dir

    @property
    def skill_library_dir(self) -> Path:
        """Legacy alias for skills_dir."""
        return self.skills_dir

    # Database
    @property
    def database_url(self) -> str:
        """Get database URL with absolute path."""
        # Use ~/.kumiai/kumiAI.db as default location
        db_path = self.kumiai_home / "kumiAI.db"
        # Fallback to legacy location if new location doesn't exist
        if not db_path.exists():
            legacy_db_path = self.base_dir / "kumiAI.db"
            if legacy_db_path.exists():
                db_path = legacy_db_path
        return f"sqlite+aiosqlite:///{db_path}"

    # Claude SDK
    claude_cwd: str = "."
    claude_setting_sources: list[str] = ["project"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
