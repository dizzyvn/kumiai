"""
Session context value object.

Provides a typed, immutable container for session configuration instead of
using magic dict keys.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass(frozen=True)
class SessionContext:
    """
    Immutable session configuration context.

    Replaces the magic dict pattern with typed properties.
    """

    # Core identifiers
    character_id: Optional[str] = None
    specialists: List[str] = field(default_factory=list)
    project_id: Optional[str] = None

    # Paths
    project_path: Optional[Path] = None
    working_directory: Optional[Path] = None

    # Session metadata
    session_id: Optional[str] = None
    instance_id: Optional[str] = None

    # Model configuration
    model: str = "sonnet"

    # Additional metadata (for extensibility)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value by key for backward compatibility with dict access.

        Args:
            key: Property name or metadata key
            default: Default value if not found

        Returns:
            Property value or default
        """
        # Try to get from main properties first
        if hasattr(self, key):
            return getattr(self, key)

        # Fall back to metadata
        return self.metadata.get(key, default)

    def with_updates(self, **kwargs) -> "SessionContext":
        """
        Create a new context with updated values.

        Since SessionContext is frozen, this creates a new instance.

        Args:
            **kwargs: Properties to update

        Returns:
            New SessionContext with updates applied
        """
        from dataclasses import replace
        return replace(self, **kwargs)
