"""
Python Provider - Native Python async function tools.

This provider allows registering Python async functions as tools without MCP overhead.
Tools follow the pattern: python__{category}__{name}

Example:
    python__analysis__custom_search
    python__utils__data_transform
"""

import logging
import inspect
from typing import Dict, List, Optional, Any, Callable, Awaitable

from ..provider_base import (
    ToolProvider,
    ToolDefinition,
    ToolContext,
    ToolResult,
    ProviderType,
    ToolImplementation
)

logger = logging.getLogger(__name__)


class PythonProvider(ToolProvider):
    """
    Python Function Tool Provider.

    Executes Python async functions directly without MCP overhead.
    Ideal for:
        - Custom business logic
        - Data transformations
        - Internal utilities
        - Performance-critical tools
    """

    def __init__(self):
        """Initialize Python provider."""
        super().__init__(ProviderType.PYTHON)
        self._implementations: Dict[str, ToolImplementation] = {}

    async def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize Python provider.

        Args:
            config: Optional configuration
                   {
                       "auto_register": [module_path, ...],  # Auto-import modules
                   }
        """
        config = config or {}
        logger.info("PythonProvider initialized")

        # TODO: Could auto-register tools from specified modules
        auto_register = config.get("auto_register", [])
        if auto_register:
            logger.info(f"Auto-registering tools from: {auto_register}")
            # Implementation for auto-registration can be added later

    async def get_tools(self, context: ToolContext) -> List[ToolDefinition]:
        """
        Get available Python tools.

        Args:
            context: Execution context (can filter tools based on permissions)

        Returns:
            List of registered Python tool definitions
        """
        # Filter tools based on context permissions if needed
        available_tools = []

        for tool_id, tool_def in self._tools.items():
            # Check if context has permission for this tool
            # For now, return all tools (permission checks can be added later)
            available_tools.append(tool_def)

        return available_tools

    async def execute_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """
        Execute a Python tool.

        Args:
            tool_id: Python tool ID (e.g., "python__analysis__custom_search")
            arguments: Tool arguments
            context: Execution context

        Returns:
            ToolResult with execution result or error
        """
        # Get tool implementation
        implementation = self._implementations.get(tool_id)

        if not implementation:
            return ToolResult.error_result(
                f"Python tool not found: {tool_id}"
            )

        try:
            # Execute the async function
            logger.info(f"Executing Python tool: {tool_id}")
            result = await implementation(arguments, context)

            return ToolResult.success_result(
                result=result,
                metadata={"tool_id": tool_id}
            )

        except Exception as e:
            error_msg = f"Python tool execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return ToolResult.error_result(error_msg)

    def register_function(
        self,
        category: str,
        name: str,
        function: Callable[[Dict[str, Any], ToolContext], Awaitable[Any]],
        description: str,
        input_schema: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a Python async function as a tool.

        Args:
            category: Tool category (e.g., "analysis", "utils")
            name: Tool name (e.g., "custom_search")
            function: Async function to execute
            description: Human-readable description
            input_schema: JSON schema for parameters
            metadata: Additional metadata

        Example:
            async def my_tool(args: Dict, context: ToolContext) -> Any:
                value = args.get("value")
                return {"result": value * 2}

            provider.register_function(
                category="math",
                name="double",
                function=my_tool,
                description="Double a number",
                input_schema={"type": "object", "properties": {"value": {"type": "number"}}}
            )
        """
        tool_id = f"python__{category}__{name}"

        # Create tool definition
        tool_def = ToolDefinition(
            tool_id=tool_id,
            provider="python",
            category=category,
            name=name,
            description=description,
            input_schema=input_schema,
            metadata=metadata or {}
        )

        # Register tool and implementation
        self.register_tool(tool_def)
        self._implementations[tool_id] = function

        logger.info(f"Registered Python tool: {tool_id}")

    def register_decorated_function(
        self,
        category: str,
        decorated_function: Any
    ) -> None:
        """
        Register a function decorated with @tool() from claude_agent_sdk.

        Args:
            category: Tool category
            decorated_function: Function decorated with @tool()

        Example:
            from claude_agent_sdk import tool

            @tool("my_tool", "Do something", {"param": str})
            async def my_tool(args: dict) -> dict:
                return {"result": args["param"]}

            provider.register_decorated_function("utils", my_tool)
        """
        # Extract metadata from decorated function
        # The @tool decorator adds __tool_name__, __tool_description__, etc.
        if not hasattr(decorated_function, "__tool_name__"):
            raise ValueError(
                f"Function {decorated_function.__name__} is not decorated with @tool()"
            )

        tool_name = getattr(decorated_function, "__tool_name__")
        tool_description = getattr(decorated_function, "__tool_description__", "")
        tool_schema = getattr(decorated_function, "__tool_schema__", {})

        # Wrap the decorated function to match our signature
        async def wrapped_implementation(args: Dict[str, Any], context: ToolContext) -> Any:
            # The decorated function expects just args
            return await decorated_function(args)

        self.register_function(
            category=category,
            name=tool_name,
            function=wrapped_implementation,
            description=tool_description,
            input_schema=tool_schema,
            metadata={"decorated": True}
        )

    def unregister_tool(self, tool_id: str) -> bool:
        """
        Unregister a Python tool.

        Args:
            tool_id: Full tool identifier

        Returns:
            True if tool was unregistered, False if not found
        """
        if tool_id in self._tools:
            del self._tools[tool_id]
            del self._implementations[tool_id]
            logger.info(f"Unregistered Python tool: {tool_id}")
            return True

        return False

    async def shutdown(self) -> None:
        """Cleanup Python provider resources."""
        logger.info(f"PythonProvider shutdown ({len(self._tools)} tools)")
        self._implementations.clear()
