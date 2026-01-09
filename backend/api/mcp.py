"""MCP server API endpoints."""
from fastapi import APIRouter
from ..utils.mcp_config import load_user_mcp_config

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/servers")
async def list_mcp_servers():
    """
    Get available MCP servers from user's configuration.

    Reads ~/.claude/mcp.json and returns available server configurations.
    """
    mcp_config = load_user_mcp_config()

    # Transform to list format with server IDs
    servers = [
        {
            "id": server_id,
            "name": config.get("name", server_id),
            "command": config.get("command"),
            "description": config.get("description", f"MCP server: {server_id}"),
        }
        for server_id, config in mcp_config.items()
    ]

    return servers
