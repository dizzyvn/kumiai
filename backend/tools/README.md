

# Hybrid Tool Provider System

A flexible, extensible tool system that supports multiple provider types beyond MCP servers.

## Overview

The tool provider system allows agents to use tools from three different sources:
- **MCP Providers** - Existing MCP servers (backward compatible)
- **Python Providers** - Native async Python functions (fast, in-process)
- **HTTP Providers** - REST API calls and webhooks (external integrations)

## Architecture

```
┌─────────────┐
│   Agent     │
└──────┬──────┘
       │
       ▼
┌──────────────────────┐
│ ToolProviderManager  │  ← Coordinates all providers
└──────┬───────────────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│MCPProvider  │   │PythonProvider│   │HTTPProvider  │
└─────────────┘   └──────────────┘   └──────────────┘
       │                 │                  │
       ▼                 ▼                  ▼
  MCP Servers    Async Functions      REST APIs
```

## Tool Naming Pattern

All tools follow the pattern: `{provider}__{category}__{name}`

### Examples:
```
mcp__gmail__send_email           # MCP server tool
python__math__calculate_metrics  # Python function
http__slack__send_message        # HTTP endpoint
```

### Why this pattern?
- **Explicit provider type** - Easy to see where tool comes from
- **Organized by category** - Group related tools (gmail, slack, math, utils)
- **Consistent parsing** - Simple `split("__", 2)` to get components
- **Backwards compatible** - Follows existing `mcp__` pattern

## Provider Types

### 1. MCPProvider (`mcp__*`)

Wraps existing MCP servers - fully backward compatible.

**When to use:**
- You have an existing MCP server (gmail, calendar, etc.)
- Complex integrations that already work
- Standard Claude Code tools

**Example:**
```python
# Skills reference MCP servers as before
allowed-mcp-servers: gmail, calendar

# Tools available:
# mcp__gmail__send_email
# mcp__gmail__search_emails
# mcp__calendar__create_event
```

### 2. PythonProvider (`python__*`)

Native Python async functions executed in-process.

**When to use:**
- Custom business logic
- Data transformations
- Calculations
- Performance-critical operations (no MCP overhead)
- Easy testing

**Example:**
```python
from tools.providers.python_provider import PythonProvider
from tools.provider_base import ToolContext

async def my_tool(args: dict, context: ToolContext):
    value = args["value"]
    return {"result": value * 2}

provider = PythonProvider()
await provider.initialize()

provider.register_function(
    category="math",
    name="double",
    function=my_tool,
    description="Double a number",
    input_schema={
        "type": "object",
        "properties": {"value": {"type": "number"}},
        "required": ["value"]
    }
)

# Tool ID: python__math__double
```

### 3. HTTPProvider (`http__*`)

Direct REST API calls without MCP setup.

**When to use:**
- External API integrations
- Webhooks
- Simple HTTP endpoints
- No need for full MCP server

**Example:**
```python
from tools.providers.http_provider import HTTPProvider

provider = HTTPProvider()
await provider.initialize({
    "endpoints": {
        "slack_webhook": {
            "url": "https://hooks.slack.com/services/YOUR/WEBHOOK",
            "method": "POST",
            "description": "Send Slack notification"
        }
    }
})

# Tool ID: http__slack__webhook

# Or use the generic HTTP tool:
# http__api__call - can call ANY URL dynamically
```

## Using Tools in Skills

Add custom tools to skill frontmatter:

```yaml
---
name: My Skill
description: Does cool stuff
allowed-tools: Read, Write           # Built-in tools
allowed-mcp-servers: gmail           # MCP servers
allowed-custom-tools:                 # Custom tools
  - python__math__calculate
  - http__slack__notify
---
```

## Integration Flow

1. **Skill defines tools** → `allowed-custom-tools` in frontmatter
2. **Character aggregates** → Collects all tools from assigned skills
3. **Provider resolves** → ToolProviderManager routes to correct provider
4. **Execution** → Tool runs and returns result

## File Structure

```
backend/tools/
├── provider_base.py          # Core abstractions
├── provider_manager.py       # Coordinator
├── providers/
│   ├── mcp_provider.py       # MCP wrapper
│   ├── python_provider.py    # Python functions
│   └── http_provider.py      # HTTP calls
├── examples/
│   ├── python_tool_example.py
│   ├── http_tool_example.py
│   └── example_skill.md
└── README.md                 # This file
```

## Quick Start

### 1. Create a Python Tool

```python
# backend/tools/my_tools.py
from tools.providers.python_provider import PythonProvider
from tools.provider_base import ToolContext

async def greet(args: dict, context: ToolContext):
    name = args.get("name", "World")
    return {"message": f"Hello, {name}!"}

def register_my_tools(provider: PythonProvider):
    provider.register_function(
        category="demo",
        name="greet",
        function=greet,
        description="Greet someone",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            }
        }
    )
    # Tool ID: python__demo__greet
```

### 2. Create a Skill

```yaml
# skill_library/greeting/skill.md
---
name: Greeting Skill
description: Greet people
allowed-custom-tools:
  - python__demo__greet
---

Use python__demo__greet to greet users.
```

### 3. Assign to Character

```yaml
# character_library/mychar/agent.md
---
name: Greeter Bot
skills: greeting
---

I greet people!
```

### 4. Register Tools (in client creation)

```python
# backend/services/claude_client.py
from tools.provider_manager import ToolProviderManager
from tools.providers import PythonProvider, HTTPProvider
from tools.my_tools import register_my_tools

# Initialize provider manager
manager = ToolProviderManager()

# Register Python provider
python_provider = PythonProvider()
await python_provider.initialize()
register_my_tools(python_provider)  # Register your custom tools
manager.register_provider(python_provider)

# Initialize manager
await manager.initialize()

# Get tools for character
custom_tools = character.capabilities["allowed_custom_tools"]
# ["python__demo__greet"]
```

## Best Practices

### Tool Design
1. **Single responsibility** - One tool does one thing well
2. **Clear schemas** - Document all parameters with types
3. **Error handling** - Return meaningful error messages
4. **Idempotent** - Same input → same output (when possible)

### Provider Selection
- **Python** for logic, calculations, transformations
- **HTTP** for external APIs, webhooks, integrations
- **MCP** for complex integrations with existing servers

### Security
- **Validate inputs** - Check schemas before execution
- **Use ToolContext** - Check permissions, session info
- **Sanitize outputs** - Don't leak sensitive data
- **Rate limiting** - Consider adding for external APIs

### Performance
- **Python tools** - Fastest (in-process)
- **HTTP tools** - Network latency
- **MCP tools** - Process spawning overhead

## Testing

### Unit Test a Python Tool
```python
import pytest
from tools.provider_base import ToolContext

@pytest.mark.asyncio
async def test_greet():
    from my_tools import greet

    context = ToolContext(character_id="test")
    result = await greet({"name": "Alice"}, context)

    assert result["message"] == "Hello, Alice!"
```

### Mock HTTP Provider
```python
@pytest.mark.asyncio
async def test_http_tool():
    provider = HTTPProvider()
    # Mock httpx responses
    # Test tool execution
```

## Examples

See `backend/tools/examples/` for:
- `python_tool_example.py` - Python tool patterns
- `http_tool_example.py` - HTTP endpoint configuration
- `example_skill.md` - Complete skill using custom tools

## Migration from MCP-only

### Before (MCP only):
```yaml
# All tools must be MCP servers
allowed-mcp-servers: custom_tools
```

### After (Hybrid):
```yaml
# Mix and match
allowed-mcp-servers: gmail        # Use MCP when it exists
allowed-custom-tools:
  - python__utils__parse          # Use Python for custom logic
  - http__slack__notify           # Use HTTP for webhooks
```

## Troubleshooting

**Tool not found**
- Check tool ID follows pattern: `provider__category__name`
- Verify tool registered with provider
- Check skill includes tool in `allowed-custom-tools`

**Tool execution fails**
- Check input schema matches arguments
- Verify provider is initialized
- Check logs for detailed error messages

**Permission denied**
- Verify ToolContext has required permissions
- Check character has skill assigned
- Verify skill includes the tool

## Tool Registry System

### Automatic Registration

All custom Python tools are automatically registered in a centralized `TOOL_REGISTRY` that maintains rich metadata for tool discovery and search capabilities.

### Registry Contents

Each registered tool has:
- `name`: Function name
- `category`: Tool category (youtube, arxiv, pdf, web, github, meta)
- `full_name`: Full registration name (e.g., `python__youtube__download_thumbnail`)
- `description`: Tool description
- `capabilities`: List of searchable keywords
- `input_params`: List of input parameter names
- `example_use_case`: Example usage scenario

### Registration Helper

Use `_register_tool()` to register new tools (automatically populates registry):

```python
from tools.custom_tools import _register_tool

_register_tool(
    provider=provider,
    category="youtube",
    name="download_thumbnail",
    function=download_youtube_thumbnail,
    description="Download YouTube video thumbnail image",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "YouTube video URL"},
            "quality": {"type": "string", "enum": ["maxresdefault", "sddefault"], "default": "maxresdefault"}
        },
        "required": ["url"]
    },
    capabilities=["download", "thumbnail", "youtube", "video", "image"],
    example_use_case="Download thumbnails for video analysis or archiving"
)
```

### Tool Discovery

The `python__meta__search_tools` tool allows agents to discover available tools:

```python
# List all tools
await search_custom_tools({"list_all": True}, context)

# Search by keyword
await search_custom_tools({"query": "pdf"}, context)

# Filter by category
await search_custom_tools({"category": "arxiv"}, context)
```

**Response format:**
```json
{
    "success": true,
    "tools": [...],
    "count": 10,
    "total_tools": 11,
    "categories": ["youtube", "arxiv", "pdf", "web", "github", "meta"],
    "query": "pdf",
    "category_filter": null
}
```

### Available Custom Tools

**YouTube Tools:**
- `python__youtube__download_thumbnail` - Download video thumbnails
- `python__youtube__download_transcript` - Download video transcripts/captions

**arXiv Tools:**
- `python__arxiv__download_paper` - Download papers with metadata
- `python__arxiv__search` - Search for papers by query

**PDF Tools:**
- `python__pdf__extract_text` - Extract text from PDF files
- `python__pdf__extract_tables` - Extract tables from PDF files
- `python__pdf__extract_figures` - Extract images/figures from PDF files
- `python__pdf__create` - Create PDF documents from text

**Web Tools:**
- `python__web__crawl` - Crawl websites and extract content (requires Python 3.10+)

**GitHub Tools:**
- `python__github__search_repos` - Search GitHub repositories with metadata

**Meta Tools:**
- `python__meta__search_tools` - Search for available custom tools (for skill-assistant agent)

See `backend/tools/custom_tools.py` for implementation details.

## Future Enhancements

Planned but not yet implemented:
- Tool caching for expensive operations
- Rate limiting per tool
- Tool usage analytics
- Tool recommendation engine
- Dynamic tool loading from plugins
- Tool composition (tools calling tools)
