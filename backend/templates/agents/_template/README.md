# Agent Configuration Template

This template provides the structure for creating new agent configurations.

## File Structure

Each agent directory should contain:
- `agent.md` - Main agent configuration with YAML frontmatter and markdown content
- `avatar.png` (optional) - Agent avatar image (auto-generated if not provided)

## agent.md Format

### YAML Frontmatter

```yaml
---
skills: skill-id-1, skill-id-2
---
```

**Fields:**
- `skills` - Comma-separated list of skill IDs that this agent can use

**Note:** The `avatar` field is auto-generated and should not be manually added.

### Markdown Content

The markdown content after the frontmatter defines the agent's:
- Role and expertise
- Key responsibilities
- Skills and capabilities
- Approach and methodology
- Communication style
- Best practices
- Example use cases

## Creating a New Agent

1. Create a new directory in `~/.kumiai/agents/` with a unique agent ID
2. Copy `agent.md` template to the new directory
3. Edit the YAML frontmatter to specify skills
4. Write the agent's personality and capabilities in markdown
5. Optionally add a custom `avatar.png` (will be auto-generated if missing)

## Tips

- Keep agent descriptions clear and focused
- List specific responsibilities and use cases
- Define communication style for consistent interactions
- Reference skill IDs that exist in `~/.kumiai/skills/`
