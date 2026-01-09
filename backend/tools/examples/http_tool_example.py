"""
Example: Creating HTTP Tools

This example shows how to create HTTP tools using the HTTPProvider.
HTTP tools can call external REST APIs and webhooks directly.
"""

from ..providers.http_provider import HTTPProvider


# ============================================================================
# Method 1: Configure endpoints at provider initialization
# ============================================================================

def get_http_provider_config() -> dict:
    """
    Example configuration for HTTP provider with pre-configured endpoints.

    Returns:
        Configuration dict for HTTPProvider.initialize()
    """
    return {
        "timeout": 30,  # Request timeout in seconds
        "endpoints": {
            # Slack webhook example
            "slack_notification": {
                "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                "method": "POST",
                "description": "Send notification to Slack channel",
                "headers": {
                    "Content-Type": "application/json"
                },
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "body": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "Message text"},
                                "channel": {"type": "string", "description": "Channel name"}
                            },
                            "required": ["text"]
                        }
                    }
                }
            },
            # Tool ID: http__slack__notification

            # Generic webhook example
            "webhook_trigger": {
                "url": "https://your-api.com/webhooks/notify",
                "method": "POST",
                "description": "Trigger a webhook with custom payload",
                "headers": {
                    "Authorization": "Bearer YOUR_API_KEY",
                    "Content-Type": "application/json"
                },
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "body": {
                            "type": "object",
                            "description": "Webhook payload"
                        }
                    },
                    "required": ["body"]
                }
            },
            # Tool ID: http__webhook__trigger

            # REST API example (GitHub)
            "github_create_issue": {
                "url": "https://api.github.com/repos/OWNER/REPO/issues",
                "method": "POST",
                "description": "Create a GitHub issue",
                "headers": {
                    "Accept": "application/vnd.github+json",
                    "Authorization": "Bearer YOUR_GITHUB_TOKEN",
                    "X-GitHub-Api-Version": "2022-11-28"
                },
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "body": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "body": {"type": "string"},
                                "labels": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            },
                            "required": ["title"]
                        }
                    }
                }
            }
            # Tool ID: http__github__create_issue
        }
    }


# ============================================================================
# Method 2: Dynamically add endpoints to provider
# ============================================================================

def add_custom_endpoints(provider: HTTPProvider) -> None:
    """
    Dynamically add HTTP endpoints to the provider.

    Args:
        provider: HTTPProvider instance
    """

    # Add a Discord webhook
    provider.add_endpoint(
        name="discord_message",
        url="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/TOKEN",
        method="POST",
        headers={"Content-Type": "application/json"},
        description="Send message to Discord channel"
    )
    # Tool ID: http__discord__message

    # Add a custom API endpoint
    provider.add_endpoint(
        name="api_search",
        url="https://your-api.com/search",
        method="GET",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        description="Search your custom API"
    )
    # Tool ID: http__api__search


# ============================================================================
# Method 3: Using the generic http__api__call tool
# ============================================================================

"""
The HTTPProvider includes a built-in generic tool: http__api__call

This tool can call ANY HTTP endpoint without pre-configuration:

{
    "tool_id": "http__api__call",
    "arguments": {
        "url": "https://api.example.com/data",
        "method": "GET",
        "headers": {
            "Authorization": "Bearer TOKEN"
        },
        "params": {
            "query": "search term"
        }
    }
}

For POST requests:
{
    "tool_id": "http__api__call",
    "arguments": {
        "url": "https://api.example.com/create",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json"
        },
        "body": {
            "name": "Test",
            "value": 123
        }
    }
}
"""


# ============================================================================
# Usage in Skill File
# ============================================================================

"""
To use HTTP tools in a skill, add to skill.md frontmatter:

---
name: External Integrations
description: Call external APIs and webhooks
allowed-tools: Read, Write
allowed-custom-tools:
  - http__slack__notification
  - http__github__create_issue
  - http__api__call
---

The agent can now call:
- http__slack__notification - Send Slack notifications
- http__github__create_issue - Create GitHub issues
- http__api__call - Call any HTTP API dynamically
"""


# ============================================================================
# Complete Example: Initialize HTTPProvider with endpoints
# ============================================================================

async def setup_http_provider_example():
    """Complete example of setting up HTTP provider with endpoints."""
    from ..providers.http_provider import HTTPProvider

    # Create provider
    provider = HTTPProvider()

    # Initialize with pre-configured endpoints
    config = get_http_provider_config()
    await provider.initialize(config)

    # Optionally add more endpoints dynamically
    add_custom_endpoints(provider)

    # Provider now has tools:
    # - http__slack__notification
    # - http__webhook__trigger
    # - http__github__create_issue
    # - http__discord__message
    # - http__api__search
    # - http__api__call (built-in)

    return provider
