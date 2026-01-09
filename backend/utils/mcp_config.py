"""MCP configuration utilities."""
import json
from pathlib import Path
from typing import Optional


def load_user_mcp_config() -> dict:
    """
    Load user's MCP server configuration from ~/.claude.json.

    Returns:
        Dictionary mapping server names to their configuration.
        Empty dict if file doesn't exist.
    """
    mcp_config_path = Path.home() / ".claude.json"

    if not mcp_config_path.exists():
        return {}

    try:
        config = json.loads(mcp_config_path.read_text())
        # Extract mcpServers section from the config
        return config.get("mcpServers", {})
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Failed to load MCP config from {mcp_config_path}: {e}")
        return {}


def filter_mcp_config(mcp_config: dict, allowed_servers: list[str]) -> dict:
    """
    Filter MCP configuration to only include allowed servers.

    Args:
        mcp_config: Full MCP configuration dictionary
        allowed_servers: List of allowed server names

    Returns:
        Filtered MCP configuration with only allowed servers
    """
    return {
        server: mcp_config[server]
        for server in allowed_servers
        if server in mcp_config
    }


def get_mcp_servers_for_character(allowed_mcp_servers: list[str]) -> dict:
    """
    Get filtered MCP server configuration for a character based on allowed servers.

    Args:
        allowed_mcp_servers: List of MCP server names allowed for this character

    Returns:
        Filtered MCP configuration dictionary
    """
    user_mcp_config = load_user_mcp_config()
    return filter_mcp_config(user_mcp_config, allowed_mcp_servers)
