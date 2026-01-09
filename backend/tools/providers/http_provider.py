"""
HTTP Provider - REST API and webhook tools.

This provider allows tools to call external HTTP APIs directly.
Tools follow the pattern: http__{category}__{name}

Example:
    http__slack__send_message
    http__webhook__trigger
    http__api__generic_call
"""

import logging
from typing import Dict, List, Optional, Any
import httpx
from enum import Enum

from ..provider_base import (
    ToolProvider,
    ToolDefinition,
    ToolContext,
    ToolResult,
    ProviderType
)

logger = logging.getLogger(__name__)


class HTTPMethod(str, Enum):
    """Supported HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class HTTPProvider(ToolProvider):
    """
    HTTP Tool Provider.

    Provides tools for calling external REST APIs and webhooks.
    Supports GET, POST, PUT, PATCH, DELETE methods.

    Categories:
        - api: Generic API calls
        - webhook: Webhook triggers
        - {custom}: Custom integrations (slack, github, etc.)
    """

    def __init__(self):
        """Initialize HTTP provider."""
        super().__init__(ProviderType.HTTP)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._endpoints: Dict[str, Dict[str, Any]] = {}
        self._register_builtin_tools()

    async def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize HTTP provider.

        Args:
            config: Optional configuration
                   {
                       "timeout": 30,  # Request timeout in seconds
                       "max_redirects": 5,
                       "endpoints": {
                           "slack_webhook": {
                               "url": "https://hooks.slack.com/...",
                               "method": "POST",
                               "headers": {...}
                           }
                       }
                   }
        """
        config = config or {}

        # Create async HTTP client
        timeout = config.get("timeout", 30)
        max_redirects = config.get("max_redirects", 5)

        self._http_client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=max_redirects
        )

        # Register configured endpoints
        self._endpoints = config.get("endpoints", {})
        for endpoint_name, endpoint_config in self._endpoints.items():
            self._register_endpoint_tool(endpoint_name, endpoint_config)

        logger.info(
            f"HTTPProvider initialized with {len(self._endpoints)} configured endpoints"
        )

    def _register_builtin_tools(self) -> None:
        """Register built-in HTTP tools."""

        # Generic HTTP call tool
        self.register_tool(ToolDefinition(
            tool_id="http__api__call",
            provider="http",
            category="api",
            name="call",
            description="Make a generic HTTP API call",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to call"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                        "description": "HTTP method",
                        "default": "GET"
                    },
                    "headers": {
                        "type": "object",
                        "description": "Request headers",
                        "default": {}
                    },
                    "body": {
                        "type": "object",
                        "description": "Request body (for POST/PUT/PATCH)",
                        "default": {}
                    },
                    "params": {
                        "type": "object",
                        "description": "URL query parameters",
                        "default": {}
                    }
                },
                "required": ["url"]
            }
        ))

    def _register_endpoint_tool(self, endpoint_name: str, endpoint_config: Dict[str, Any]) -> None:
        """
        Register a configured endpoint as a tool.

        Args:
            endpoint_name: Name of the endpoint (e.g., "slack_webhook")
            endpoint_config: Endpoint configuration with url, method, headers
        """
        # Parse category from endpoint name (e.g., "slack_webhook" -> "slack")
        parts = endpoint_name.split("_", 1)
        category = parts[0] if len(parts) > 0 else "custom"
        name = parts[1] if len(parts) > 1 else endpoint_name

        tool_id = f"http__{category}__{name}"

        tool_def = ToolDefinition(
            tool_id=tool_id,
            provider="http",
            category=category,
            name=name,
            description=endpoint_config.get("description", f"Call {endpoint_name} endpoint"),
            input_schema=endpoint_config.get("input_schema", {
                "type": "object",
                "properties": {
                    "body": {"type": "object", "description": "Request body"}
                }
            }),
            metadata={
                "endpoint_name": endpoint_name,
                "url": endpoint_config.get("url"),
                "method": endpoint_config.get("method", "POST")
            }
        )

        self.register_tool(tool_def)
        logger.info(f"Registered HTTP endpoint tool: {tool_id}")

    async def get_tools(self, context: ToolContext) -> List[ToolDefinition]:
        """
        Get available HTTP tools.

        Args:
            context: Execution context

        Returns:
            List of HTTP tool definitions
        """
        return list(self._tools.values())

    async def execute_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """
        Execute an HTTP tool.

        Args:
            tool_id: HTTP tool ID (e.g., "http__api__call")
            arguments: Tool arguments
            context: Execution context

        Returns:
            ToolResult with HTTP response or error
        """
        if not self._http_client:
            return ToolResult.error_result("HTTP client not initialized")

        try:
            # Route to appropriate handler
            if tool_id == "http__api__call":
                result = await self._generic_api_call(arguments)
            else:
                # Check if this is a configured endpoint
                tool_def = self.get_tool_definition(tool_id)
                if tool_def and "endpoint_name" in tool_def.metadata:
                    result = await self._call_configured_endpoint(tool_def, arguments)
                else:
                    return ToolResult.error_result(f"Unknown HTTP tool: {tool_id}")

            return ToolResult.success_result(
                result=result,
                metadata={"tool_id": tool_id}
            )

        except Exception as e:
            error_msg = f"HTTP tool execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return ToolResult.error_result(error_msg)

    async def _generic_api_call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a generic HTTP API call.

        Args:
            args: Tool arguments with url, method, headers, body, params

        Returns:
            HTTP response data
        """
        url = args["url"]
        method = args.get("method", "GET").upper()
        headers = args.get("headers", {})
        body = args.get("body")
        params = args.get("params", {})

        logger.info(f"Making {method} request to {url}")

        response = await self._http_client.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body else None,
            params=params
        )

        # Parse response
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body,
            "success": 200 <= response.status_code < 300
        }

    async def _call_configured_endpoint(
        self,
        tool_def: ToolDefinition,
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a pre-configured endpoint.

        Args:
            tool_def: Tool definition with endpoint metadata
            args: Tool arguments

        Returns:
            HTTP response data
        """
        endpoint_name = tool_def.metadata["endpoint_name"]
        endpoint_config = self._endpoints[endpoint_name]

        url = endpoint_config["url"]
        method = endpoint_config.get("method", "POST").upper()
        headers = endpoint_config.get("headers", {})

        # Merge provided body with default body
        body = {**endpoint_config.get("body", {}), **args.get("body", {})}

        logger.info(f"Calling configured endpoint {endpoint_name}: {method} {url}")

        response = await self._http_client.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body else None
        )

        # Parse response
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body,
            "success": 200 <= response.status_code < 300,
            "endpoint": endpoint_name
        }

    def add_endpoint(
        self,
        name: str,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        description: Optional[str] = None
    ) -> None:
        """
        Dynamically add an HTTP endpoint as a tool.

        Args:
            name: Endpoint name (e.g., "slack_webhook")
            url: Full URL
            method: HTTP method (default: POST)
            headers: Default headers
            description: Tool description
        """
        endpoint_config = {
            "url": url,
            "method": method,
            "headers": headers or {},
            "description": description
        }

        self._endpoints[name] = endpoint_config
        self._register_endpoint_tool(name, endpoint_config)

        logger.info(f"Added HTTP endpoint: {name}")

    async def shutdown(self) -> None:
        """Cleanup HTTP provider resources."""
        if self._http_client:
            await self._http_client.aclose()
            logger.info("HTTPProvider shutdown")
