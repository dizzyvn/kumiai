"""
Tool Provider Manager - Aggregates and routes tool execution across all providers.

This manager coordinates between MCPProvider, PythonProvider, and HTTPProvider
to provide a unified tool execution interface.
"""

import logging
from typing import Dict, List, Optional, Set
from .provider_base import (
    ToolProvider,
    ToolDefinition,
    ToolContext,
    ToolResult,
    ProviderType
)

logger = logging.getLogger(__name__)


class ToolProviderManager:
    """
    Manages multiple tool providers and routes tool execution.

    Responsibilities:
        - Register and initialize all tool providers
        - Aggregate tools from all providers
        - Route tool execution to appropriate provider
        - Handle provider lifecycle (init, shutdown)
    """

    def __init__(self):
        """Initialize the provider manager."""
        self._providers: Dict[str, ToolProvider] = {}
        self._initialized = False

    def register_provider(self, provider: ToolProvider) -> None:
        """
        Register a tool provider.

        Args:
            provider: ToolProvider instance to register
        """
        provider_key = provider.provider_type.value
        if provider_key in self._providers:
            logger.warning(f"Provider {provider_key} already registered, replacing")

        self._providers[provider_key] = provider
        logger.info(f"Registered provider: {provider_key}")

    async def initialize(self, configs: Optional[Dict[str, Dict]] = None) -> None:
        """
        Initialize all registered providers.

        Args:
            configs: Provider-specific configs keyed by provider type
                    Example: {"mcp": {...}, "python": {...}}
        """
        if self._initialized:
            logger.warning("Provider manager already initialized")
            return

        configs = configs or {}

        for provider_key, provider in self._providers.items():
            try:
                provider_config = configs.get(provider_key, {})
                await provider.initialize(provider_config)
                logger.info(f"Initialized provider: {provider_key}")
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider_key}: {e}")
                raise

        self._initialized = True
        logger.info(f"Provider manager initialized with {len(self._providers)} providers")

    async def get_all_tools(self, context: ToolContext) -> List[ToolDefinition]:
        """
        Get all available tools from all providers.

        Args:
            context: Execution context for filtering tools

        Returns:
            Combined list of all available tools
        """
        if not self._initialized:
            raise RuntimeError("Provider manager not initialized")

        all_tools = []

        for provider_key, provider in self._providers.items():
            try:
                tools = await provider.get_tools(context)
                all_tools.extend(tools)
                logger.debug(f"Provider {provider_key} provided {len(tools)} tools")
            except Exception as e:
                logger.error(f"Error getting tools from provider {provider_key}: {e}")
                # Continue with other providers

        logger.info(f"Total tools available: {len(all_tools)}")
        return all_tools

    async def get_tools_by_ids(
        self,
        tool_ids: List[str],
        context: ToolContext
    ) -> List[ToolDefinition]:
        """
        Get specific tools by their IDs.

        Args:
            tool_ids: List of tool IDs to retrieve
            context: Execution context

        Returns:
            List of matching tool definitions
        """
        if not self._initialized:
            raise RuntimeError("Provider manager not initialized")

        all_tools = await self.get_all_tools(context)
        tool_map = {tool.tool_id: tool for tool in all_tools}

        requested_tools = []
        for tool_id in tool_ids:
            if tool_id in tool_map:
                requested_tools.append(tool_map[tool_id])
            else:
                logger.warning(f"Requested tool not found: {tool_id}")

        return requested_tools

    async def execute_tool(
        self,
        tool_id: str,
        arguments: Dict,
        context: ToolContext
    ) -> ToolResult:
        """
        Execute a tool by routing to appropriate provider.

        Args:
            tool_id: Full tool identifier (e.g., "db__character__list_all")
            arguments: Tool parameters
            context: Execution context

        Returns:
            ToolResult from execution
        """
        if not self._initialized:
            raise RuntimeError("Provider manager not initialized")

        # Find provider that supports this tool
        provider = self._find_provider_for_tool(tool_id)

        if not provider:
            error_msg = f"No provider found for tool: {tool_id}"
            logger.error(error_msg)
            return ToolResult.error_result(error_msg)

        try:
            logger.info(f"Executing tool {tool_id} via {provider.provider_type.value} provider")
            result = await provider.execute_tool(tool_id, arguments, context)
            return result
        except Exception as e:
            error_msg = f"Tool execution failed for {tool_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return ToolResult.error_result(error_msg)

    def _find_provider_for_tool(self, tool_id: str) -> Optional[ToolProvider]:
        """
        Find the provider that handles a given tool.

        Args:
            tool_id: Full tool identifier

        Returns:
            ToolProvider that supports the tool, or None
        """
        for provider in self._providers.values():
            if provider.supports_tool(tool_id):
                return provider

        return None

    async def shutdown(self) -> None:
        """Shutdown all providers and cleanup resources."""
        logger.info("Shutting down provider manager")

        for provider_key, provider in self._providers.items():
            try:
                await provider.shutdown()
                logger.info(f"Shutdown provider: {provider_key}")
            except Exception as e:
                logger.error(f"Error shutting down provider {provider_key}: {e}")

        self._initialized = False
        logger.info("Provider manager shutdown complete")

    def get_provider(self, provider_type: ProviderType) -> Optional[ToolProvider]:
        """
        Get a specific provider by type.

        Args:
            provider_type: Type of provider to retrieve

        Returns:
            ToolProvider instance or None if not registered
        """
        return self._providers.get(provider_type.value)

    def list_providers(self) -> List[str]:
        """
        List all registered provider types.

        Returns:
            List of provider type names
        """
        return list(self._providers.keys())

    async def get_tools_by_provider(
        self,
        provider_type: ProviderType,
        context: ToolContext
    ) -> List[ToolDefinition]:
        """
        Get tools from a specific provider.

        Args:
            provider_type: Provider to query
            context: Execution context

        Returns:
            List of tools from that provider
        """
        provider = self.get_provider(provider_type)
        if not provider:
            logger.warning(f"Provider not found: {provider_type.value}")
            return []

        return await provider.get_tools(context)

    def parse_tool_id(self, tool_id: str) -> Optional[tuple[str, str, str]]:
        """
        Parse tool ID into components.

        Args:
            tool_id: Full tool identifier (e.g., "db__character__list_all")

        Returns:
            Tuple of (provider, category, name) or None if invalid format
        """
        parts = tool_id.split("__", 2)
        if len(parts) != 3:
            logger.error(f"Invalid tool_id format: {tool_id}")
            return None

        return tuple(parts)

    async def get_tools_by_category(
        self,
        provider_type: ProviderType,
        category: str,
        context: ToolContext
    ) -> List[ToolDefinition]:
        """
        Get tools from a specific provider and category.

        Args:
            provider_type: Provider to query
            category: Tool category (e.g., "character", "project")
            context: Execution context

        Returns:
            List of matching tools
        """
        tools = await self.get_tools_by_provider(provider_type, context)
        return [tool for tool in tools if tool.category == category]
