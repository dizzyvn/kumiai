"""
MCP Provider - Wraps existing MCP server functionality.

This provider maintains backward compatibility with the existing MCP system
while integrating with the new provider abstraction layer.
"""

import logging
from typing import Dict, List, Optional, Any

from ..provider_base import (
    ToolProvider,
    ToolDefinition,
    ToolContext,
    ToolResult,
    ProviderType
)
from ...utils.mcp_config import (
    load_user_mcp_config,
    filter_mcp_config,
    get_mcp_servers_for_character
)

logger = logging.getLogger(__name__)


class MCPProvider(ToolProvider):
    """
    MCP Server Tool Provider.

    Wraps existing MCP server integration to work with the new provider system.
    Tools follow the pattern: mcp__{server_name}__*

    Example:
        mcp__gmail__send_email
        mcp__calendar__create_event
    """

    def __init__(self):
        """Initialize MCP provider."""
        super().__init__(ProviderType.MCP)
        self._mcp_config: Dict[str, Any] = {}
        self._allowed_servers: List[str] = []

    async def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize MCP provider.

        Args:
            config: Optional configuration
                   {
                       "allowed_servers": ["gmail", "calendar", ...],
                       "user_config_path": "~/.claude.json"  # optional override
                   }
        """
        config = config or {}

        # Load user's MCP configuration
        self._mcp_config = load_user_mcp_config()

        # Get allowed servers from config
        self._allowed_servers = config.get("allowed_servers", [])

        if self._allowed_servers:
            # Filter to only allowed servers
            self._mcp_config = filter_mcp_config(self._mcp_config, self._allowed_servers)

        logger.info(
            f"MCPProvider initialized with {len(self._mcp_config)} servers: "
            f"{list(self._mcp_config.keys())}"
        )

    async def get_tools(self, context: ToolContext) -> List[ToolDefinition]:
        """
        Get available MCP tools.

        Note: MCP tools are discovered dynamically by the Claude SDK.
        This method returns placeholder definitions for MCP server prefixes.

        Args:
            context: Execution context (unused for MCP)

        Returns:
            List of MCP server tool prefixes
        """
        tools = []

        # Return MCP server prefixes as "tools"
        # The actual tool discovery happens in the Claude SDK
        for server_name, server_config in self._mcp_config.items():
            # Create a wildcard tool definition for this MCP server
            tool_id = f"mcp__{server_name}"
            tool_def = ToolDefinition(
                tool_id=tool_id,
                provider="mcp",
                category=server_name,
                name="*",  # Wildcard - actual tools discovered by SDK
                description=f"MCP server: {server_name}",
                input_schema={},  # SDK handles schema
                metadata={
                    "server_config": server_config,
                    "server_name": server_name
                }
            )
            tools.append(tool_def)

        return tools

    async def execute_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """
        Execute MCP tool.

        Note: MCP tool execution is handled by the Claude SDK.
        This method is a passthrough - actual execution happens in the SDK layer.

        Args:
            tool_id: MCP tool ID (e.g., "mcp__gmail__send_email")
            arguments: Tool arguments
            context: Execution context

        Returns:
            ToolResult indicating SDK should handle execution
        """
        # Parse tool ID
        parts = tool_id.split("__", 2)
        if len(parts) < 2:
            return ToolResult.error_result(
                f"Invalid MCP tool ID format: {tool_id}"
            )

        server_name = parts[1] if len(parts) >= 2 else ""

        # Verify server is allowed
        if server_name not in self._mcp_config:
            return ToolResult.error_result(
                f"MCP server not allowed or not found: {server_name}"
            )

        # Return success with metadata indicating SDK should handle this
        # The actual execution happens in the Claude SDK layer
        return ToolResult.success_result(
            result={
                "message": "MCP tool execution delegated to Claude SDK",
                "tool_id": tool_id,
                "server_name": server_name,
                "arguments": arguments
            },
            metadata={
                "delegate_to_sdk": True,
                "server_config": self._mcp_config[server_name]
            }
        )

    def get_mcp_config(self) -> Dict[str, Any]:
        """
        Get the filtered MCP configuration.

        Returns:
            Dictionary of MCP server configurations
        """
        return self._mcp_config.copy()

    def get_mcp_config_for_servers(self, server_names: List[str]) -> Dict[str, Any]:
        """
        Get MCP configuration for specific servers.

        Args:
            server_names: List of server names to include

        Returns:
            Filtered MCP configuration
        """
        return filter_mcp_config(self._mcp_config, server_names)

    def supports_tool(self, tool_id: str) -> bool:
        """
        Check if this provider handles the given tool.

        Args:
            tool_id: Full tool identifier

        Returns:
            True if tool is an MCP tool
        """
        return tool_id.startswith("mcp__")

    async def shutdown(self) -> None:
        """Cleanup MCP provider resources."""
        logger.info("MCPProvider shutdown")
        # MCP servers are managed by Claude SDK, no cleanup needed here
