"""
Example: Creating Python Tools

This example shows how to create custom Python tools using the PythonProvider.
Python tools execute in-process with no MCP overhead, making them ideal for:
- Custom business logic
- Data transformations
- Performance-critical operations
"""

from typing import Dict, Any
from ..provider_base import ToolContext
from ..providers.python_provider import PythonProvider


# ============================================================================
# Method 1: Simple async function
# ============================================================================

async def text_transform(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Transform text in various ways.

    Args:
        args: {"text": str, "operation": str}
              operation can be: "uppercase", "lowercase", "reverse"
        context: Tool execution context

    Returns:
        {"result": str}
    """
    text = args.get("text", "")
    operation = args.get("operation", "uppercase")

    if operation == "uppercase":
        result = text.upper()
    elif operation == "lowercase":
        result = text.lower()
    elif operation == "reverse":
        result = text[::-1]
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return {"result": result}


# ============================================================================
# Method 2: Function with more complex logic
# ============================================================================

async def calculate_metrics(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Calculate various metrics from a list of numbers.

    Args:
        args: {"numbers": List[float]}
        context: Tool execution context

    Returns:
        {
            "sum": float,
            "mean": float,
            "min": float,
            "max": float,
            "count": int
        }
    """
    numbers = args.get("numbers", [])

    if not numbers:
        return {
            "error": "No numbers provided",
            "sum": 0,
            "mean": 0,
            "min": 0,
            "max": 0,
            "count": 0
        }

    return {
        "sum": sum(numbers),
        "mean": sum(numbers) / len(numbers),
        "min": min(numbers),
        "max": max(numbers),
        "count": len(numbers)
    }


# ============================================================================
# Method 3: Using context for permissions/session info
# ============================================================================

async def get_session_info(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Get information about the current execution context.

    Args:
        args: {}
        context: Tool execution context

    Returns:
        Session and permission information
    """
    return {
        "character_id": context.character_id,
        "session_id": context.session_id,
        "project_id": context.project_id,
        "working_directory": context.working_directory,
        "permissions": list(context.permissions),
        "has_write_access": "write" in context.permissions
    }


# ============================================================================
# Registration Example
# ============================================================================

def register_example_tools(provider: PythonProvider) -> None:
    """
    Register all example tools with the Python provider.

    Args:
        provider: PythonProvider instance
    """

    # Register text_transform tool
    provider.register_function(
        category="utils",
        name="text_transform",
        function=text_transform,
        description="Transform text (uppercase, lowercase, reverse)",
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to transform"
                },
                "operation": {
                    "type": "string",
                    "enum": ["uppercase", "lowercase", "reverse"],
                    "description": "Transformation operation"
                }
            },
            "required": ["text", "operation"]
        }
    )
    # Tool ID: python__utils__text_transform

    # Register calculate_metrics tool
    provider.register_function(
        category="math",
        name="calculate_metrics",
        function=calculate_metrics,
        description="Calculate statistics (sum, mean, min, max) from numbers",
        input_schema={
            "type": "object",
            "properties": {
                "numbers": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of numbers to analyze"
                }
            },
            "required": ["numbers"]
        }
    )
    # Tool ID: python__math__calculate_metrics

    # Register get_session_info tool
    provider.register_function(
        category="system",
        name="get_session_info",
        function=get_session_info,
        description="Get current session and context information",
        input_schema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    # Tool ID: python__system__get_session_info


# ============================================================================
# Usage in Skill File
# ============================================================================

"""
To use these tools in a skill, add to skill.md frontmatter:

---
name: Text Processing
description: Advanced text and data processing utilities
allowed-tools: Read, Write
allowed-custom-tools: python__utils__text_transform, python__math__calculate_metrics
---

The agent can now call:
- python__utils__text_transform
- python__math__calculate_metrics
"""
