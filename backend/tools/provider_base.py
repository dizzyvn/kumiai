"""
Core abstraction layer for the Hybrid Tool Provider System.

This module defines the base classes and protocols for tool providers,
following the pattern: {provider}__{category}__{tool_name}

Examples:
    - mcp__gmail__send_email
    - http__slack__send_message
    - python__analysis__custom_search
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class ProviderType(Enum):
    """Supported provider types."""
    MCP = "mcp"
    PYTHON = "python"
    HTTP = "http"


@dataclass
class ToolDefinition:
    """
    Standardized tool definition across all providers.

    Attributes:
        tool_id: Full tool identifier (e.g., "db__character__list_all")
        provider: Provider type (mcp, python, db, http)
        category: Tool category/namespace (e.g., "character", "slack")
        name: Tool name (e.g., "list_all", "send_message")
        description: Human-readable description
        input_schema: JSON schema for tool parameters
        metadata: Additional provider-specific metadata
    """
    tool_id: str
    provider: str
    category: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_tool_id(cls, tool_id: str, description: str, input_schema: Dict[str, Any],
                     metadata: Optional[Dict[str, Any]] = None) -> "ToolDefinition":
        """
        Create ToolDefinition from tool_id following pattern: provider__category__name

        Args:
            tool_id: Full tool identifier (e.g., "db__character__list_all")
            description: Tool description
            input_schema: JSON schema for parameters
            metadata: Additional metadata

        Returns:
            ToolDefinition instance

        Raises:
            ValueError: If tool_id doesn't match expected pattern
        """
        parts = tool_id.split("__", 2)
        if len(parts) != 3:
            raise ValueError(
                f"Invalid tool_id format: {tool_id}. "
                f"Expected: provider__category__name"
            )

        provider, category, name = parts

        return cls(
            tool_id=tool_id,
            provider=provider,
            category=category,
            name=name,
            description=description,
            input_schema=input_schema,
            metadata=metadata or {}
        )


@dataclass
class ToolContext:
    """
    Execution context provided to tool providers.

    Attributes:
        character_id: ID of the character executing the tool
        session_id: Current session ID
        project_id: Current project ID
        user_id: User ID (if applicable)
        permissions: Set of allowed actions/resources
        working_directory: Current working directory
        extra: Additional context data
    """
    character_id: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    permissions: set = field(default_factory=set)
    working_directory: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """
    Standardized result from tool execution.

    Attributes:
        success: Whether execution succeeded
        result: Tool output (if successful)
        error: Error message (if failed)
        metadata: Additional execution metadata (timing, logs, etc.)
    """
    success: bool
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_result(cls, result: Any, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """Create successful result."""
        return cls(success=True, result=result, metadata=metadata or {})

    @classmethod
    def error_result(cls, error: str, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """Create error result."""
        return cls(success=False, error=error, metadata=metadata or {})


class ToolProvider(ABC):
    """
    Abstract base class for all tool providers.

    Each provider type (MCP, Python, HTTP) implements this interface
    to provide a unified tool execution system.
    """

    def __init__(self, provider_type: ProviderType):
        """
        Initialize tool provider.

        Args:
            provider_type: Type of provider (MCP, Python, Database, HTTP)
        """
        self.provider_type = provider_type
        self._tools: Dict[str, ToolDefinition] = {}

    @abstractmethod
    async def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the provider with configuration.

        Args:
            config: Provider-specific configuration
        """
        pass

    @abstractmethod
    async def get_tools(self, context: ToolContext) -> List[ToolDefinition]:
        """
        Get list of available tools for given context.

        Args:
            context: Execution context (character, session, permissions)

        Returns:
            List of available tool definitions
        """
        pass

    @abstractmethod
    async def execute_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """
        Execute a tool with given arguments.

        Args:
            tool_id: Full tool identifier (e.g., "db__character__list_all")
            arguments: Tool parameters
            context: Execution context

        Returns:
            ToolResult with success/error status and result
        """
        pass

    def supports_tool(self, tool_id: str) -> bool:
        """
        Check if this provider handles the given tool.

        Args:
            tool_id: Full tool identifier

        Returns:
            True if provider supports this tool
        """
        return tool_id.startswith(f"{self.provider_type.value}__")

    def register_tool(self, tool: ToolDefinition) -> None:
        """
        Register a tool with this provider.

        Args:
            tool: Tool definition to register
        """
        self._tools[tool.tool_id] = tool

    def get_tool_definition(self, tool_id: str) -> Optional[ToolDefinition]:
        """
        Get tool definition by ID.

        Args:
            tool_id: Full tool identifier

        Returns:
            ToolDefinition if found, None otherwise
        """
        return self._tools.get(tool_id)

    async def shutdown(self) -> None:
        """
        Cleanup provider resources.

        Override this method if provider needs cleanup (close connections, etc.)
        """
        pass


# Type alias for tool implementation functions
ToolImplementation = Callable[[Dict[str, Any], ToolContext], Any]
