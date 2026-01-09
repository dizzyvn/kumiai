"""
Centralized MCP server configuration management.

This service provides a single point for loading and caching MCP server
configurations from ~/.claude.json and resolving custom tools.
"""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class MCPServerService:
    """
    Singleton service for MCP server configuration management.

    Responsibilities:
    - Load user MCP config from ~/.claude.json
    - Filter MCP servers for specific characters
    - Resolve custom tools from skill/character definitions
    - Cache expensive operations
    """

    _instance: Optional["MCPServerService"] = None

    def __init__(self):
        """Initialize service with empty caches."""
        self._user_config: Optional[Dict[str, Any]] = None
        self._server_cache: Dict[str, Dict[str, Any]] = {}
        self._custom_tool_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "MCPServerService":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = MCPServerService()
            logger.info("[MCP_SERVICE] Initialized MCPServerService singleton")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (useful for testing)."""
        cls._instance = None

    def load_user_config(self) -> Dict[str, Any]:
        """
        Load and cache user MCP config from ~/.claude.json.

        Returns:
            Dict mapping server names to their configurations
        """
        if self._user_config is None:
            from backend.utils.mcp_config import load_user_mcp_config
            self._user_config = load_user_mcp_config()
            logger.info(f"[MCP_SERVICE] Loaded user MCP config: {len(self._user_config)} servers")
        return self._user_config

    def get_servers_for_character(
        self,
        character_id: str,
        allowed_mcp_servers: List[str]
    ) -> Dict[str, Any]:
        """
        Get filtered MCP servers for a character based on allowed list.

        Args:
            character_id: Character identifier (for cache key)
            allowed_mcp_servers: List of MCP server names the character can use

        Returns:
            Dict mapping server names to their configurations (filtered)
        """
        if not allowed_mcp_servers:
            return {}

        # Create cache key from character and allowed servers
        cache_key = f"{character_id}:{','.join(sorted(allowed_mcp_servers))}"

        if cache_key not in self._server_cache:
            from backend.utils.mcp_config import filter_mcp_config

            user_config = self.load_user_config()
            filtered_servers = filter_mcp_config(user_config, allowed_mcp_servers)

            self._server_cache[cache_key] = filtered_servers

            logger.info(
                f"[MCP_SERVICE] Loaded {len(filtered_servers)} MCP servers for {character_id}: "
                f"{list(filtered_servers.keys())}"
            )

            if not filtered_servers and allowed_mcp_servers:
                logger.warning(
                    f"[MCP_SERVICE] No MCP servers found for {character_id}! "
                    f"Requested: {allowed_mcp_servers}. Check ~/.claude.json"
                )
        else:
            logger.debug(f"[MCP_SERVICE] Using cached MCP servers for {cache_key}")

        return self._server_cache[cache_key]

    async def resolve_custom_tools(
        self,
        tool_ids: List[str],
        character_id: str,
        project_path: str,
        session_id: str,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolve custom tools from skill/character definitions.

        Args:
            tool_ids: List of custom tool identifiers
            character_id: Character requesting the tools
            project_path: Project working directory
            session_id: Session identifier
            project_id: Optional project ID

        Returns:
            Dict mapping tool names to their MCP server configurations
        """
        if not tool_ids:
            return {}

        # Cache key based on tool IDs (custom tools are session-specific, so include session_id)
        cache_key = f"{character_id}:{session_id}:{','.join(sorted(tool_ids))}"

        if cache_key not in self._custom_tool_cache:
            from backend.services.claude_client import resolve_custom_tools

            logger.info(
                f"[MCP_SERVICE] Resolving {len(tool_ids)} custom tools for {character_id}: {tool_ids}"
            )

            custom_mcp = await resolve_custom_tools(
                custom_tool_ids=tool_ids,
                character_id=character_id,
                project_path=project_path,
                session_id=session_id,
                project_id=project_id,
            )

            self._custom_tool_cache[cache_key] = custom_mcp

            logger.info(
                f"[MCP_SERVICE] Resolved {len(custom_mcp)} custom tool MCP servers for {character_id}"
            )
        else:
            logger.debug(f"[MCP_SERVICE] Using cached custom tools for {cache_key}")

        return self._custom_tool_cache[cache_key]

    def clear_cache(self):
        """Clear all caches (useful for development/testing)."""
        self._user_config = None
        self._server_cache.clear()
        self._custom_tool_cache.clear()
        logger.info("[MCP_SERVICE] Cleared all caches")
