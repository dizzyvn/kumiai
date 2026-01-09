"""Skill Assistant Tools.

These tools enable the skill-assistant agent to discover and recommend
available custom tools when helping users build skills, as well as
manage skills (CRUD operations).

Meta tools are separate from customized tools - they're for the skill-assistant's
internal use, not for assignment to specialists.
"""
from claude_agent_sdk import tool
from typing import Any
import logging

from .custom_tools import TOOL_REGISTRY
from .skill_tools import search_skills, list_skills, get_skill, create_skill, update_skill

logger = logging.getLogger(__name__)


@tool(
    "search_custom_tools",
    "Search for available custom tools by keyword, category, or list all tools",
    {
        "query": str,  # Optional search keyword
        "category": str,  # Optional category filter
        "list_all": bool,  # Optional flag to list all tools
    }
)
async def search_custom_tools(args: dict[str, Any]) -> dict[str, Any]:
    """Search for available custom tools (skill-assistant only).

    This tool helps the skill-assistant discover what custom tools are available
    so it can recommend appropriate tools when helping users build skills.

    Args:
        query: Optional search keyword to find tools (searches name, description, capabilities)
        category: Optional category filter (youtube, arxiv, pdf, web, github)
        list_all: If true, list all available tools (default: false)

    Returns:
        List of matching tools with their metadata

    Examples:
        - search_custom_tools({"list_all": true}) - List all tools
        - search_custom_tools({"query": "pdf"}) - Find PDF-related tools
        - search_custom_tools({"category": "arxiv"}) - List arXiv tools
    """
    try:
        query = args.get("query", "").lower()
        category_filter = args.get("category", "").lower()
        list_all = args.get("list_all", False)

        logger.info(f"[SKILL_ASSISTANT_TOOLS] search_custom_tools called: query='{query}', category='{category_filter}', list_all={list_all}")

        # Get tools from the registry (automatically populated during registration)
        tools_catalog = list(TOOL_REGISTRY.values())

        # Filter out meta tools from the search results (they're for skill-assistant only)
        tools_catalog = [t for t in tools_catalog if t.get("category") != "meta"]

        # Filter tools based on criteria
        results = []

        for tool in tools_catalog:
            # If list_all is true, include all tools
            if list_all:
                results.append(tool)
                continue

            # Filter by category if specified
            if category_filter and tool["category"] != category_filter:
                continue

            # Filter by query if specified
            if query:
                searchable = (
                    f"{tool['name']} "
                    f"{tool['category']} "
                    f"{tool['description']} "
                    f"{' '.join(tool['capabilities'])} "
                    f"{tool['example_use_case']}"
                ).lower()

                if query in searchable:
                    results.append(tool)
            elif not category_filter:
                # If no query and no category, return all
                results.append(tool)
            else:
                # Category filter only
                results.append(tool)

        # Get unique categories (excluding meta)
        categories = sorted(list(set(tool["category"] for tool in tools_catalog)))

        # Format results as readable text
        result_lines = ["📚 Available Custom Tools", ""]
        result_lines.append(f"Total: {len(results)} tool{'s' if len(results) != 1 else ''}")

        if query:
            result_lines.append(f"Search: '{query}'")
        if category_filter:
            result_lines.append(f"Category: {category_filter}")

        result_lines.append(f"Categories: {', '.join(categories)}")
        result_lines.append("")

        # Group by category
        by_category = {}
        for tool in results:
            cat = tool["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(tool)

        # Format output
        for cat in sorted(by_category.keys()):
            result_lines.append(f"## {cat.upper()}")
            result_lines.append("")
            for tool in by_category[cat]:
                result_lines.append(f"**{tool['full_name']}**")
                result_lines.append(f"  {tool['description']}")
                result_lines.append(f"  Inputs: {', '.join(tool['input_params'])}")
                result_lines.append(f"  Example: {tool['example_use_case']}")
                result_lines.append("")

        if len(results) == 0:
            result_lines.append("No tools found matching your criteria.")
            result_lines.append("")
            result_lines.append(f"Available categories: {', '.join(categories)}")

        logger.info(f"[SKILL_ASSISTANT_TOOLS] Found {len(results)} tools")

        return {
            "content": [{
                "type": "text",
                "text": "\n".join(result_lines)
            }]
        }

    except Exception as e:
        logger.error(f"[SKILL_ASSISTANT_TOOLS] Error searching tools: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"✗ Failed to search custom tools: {str(e)}"
            }]
        }


# Tool collection for skill-assistant
# Includes: custom tool discovery + skill management (CRUD)
SKILL_ASSISTANT_TOOLS = [
    search_custom_tools,  # Discovery tool for custom tools
    search_skills,        # Search for skills
    list_skills,          # List all skills
    get_skill,            # Get skill details
    create_skill,         # Create new skill
    update_skill          # Update existing skill
]
