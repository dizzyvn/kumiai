# Skill Configuration Template

This template provides the structure for creating new skill definitions.

## File Structure

Each skill directory should contain:
- `skill.md` - Main skill definition with YAML frontmatter and markdown content

## skill.md Format

### YAML Frontmatter

```yaml
---
name: skill-name
description: Brief description of what this skill does and when to use it.
license: Apache-2.0
version: 1.0.0
category: general
---
```

**Required Fields:**
- `name` - Unique skill identifier (lowercase, hyphen-separated)
- `description` - Brief description of the skill and when to use it
- `license` - License type (e.g., Apache-2.0, MIT)
- `version` - Semantic version number (e.g., 1.0.0)

**Optional Fields:**
- `category` - Skill category (e.g., general, development, research, design)

### Markdown Content

The markdown content after the frontmatter defines:
- **When to Use This Skill** - Specific use cases and scenarios
- **Core Concepts** - Main concepts and capabilities
- **Best Practices** - Guidelines for effective use
- **Common Patterns** - Reusable patterns and approaches
- **Examples** - Concrete examples with descriptions
- **Tips and Tricks** - Helpful tips for users
- **Common Pitfalls** - What to avoid and why
- **Resources** - Additional references and materials

## Creating a New Skill

1. Create a new directory in `~/.kumiai/skills/` with the skill name
2. Copy `skill.md` template to the new directory
3. Edit the YAML frontmatter with skill metadata
4. Write the skill content in markdown following the template structure
5. Include practical examples and use cases

## Tips

- Keep descriptions clear and actionable
- Include specific use cases and examples
- Document best practices and common pitfalls
- Use consistent formatting and structure
- Version your skills semantically (major.minor.patch)

## Skill Categories

Common skill categories include:
- `development` - Software development and programming
- `research` - Research and analysis skills
- `design` - Design and architecture skills
- `testing` - Testing and quality assurance
- `documentation` - Documentation and writing
- `devops` - DevOps and infrastructure
- `general` - General purpose skills
