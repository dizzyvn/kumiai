"""Utility for generating human-readable slugs from names."""
import re
import uuid


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a URL-safe slug.

    Args:
        text: Text to convert to slug
        max_length: Maximum length of the slug (excluding suffix)

    Returns:
        Lowercase slug with hyphens instead of spaces

    Examples:
        "Market Researcher" -> "market-researcher"
        "Data Analyst (ML)" -> "data-analyst-ml"
        "Product Manager #1" -> "product-manager-1"
    """
    # Convert to lowercase
    slug = text.lower()

    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)

    # Remove special characters, keep only alphanumeric and hyphens
    slug = re.sub(r'[^a-z0-9-]', '', slug)

    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    # Truncate to max length
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('-')

    # Ensure slug is not empty
    if not slug:
        slug = 'agent'

    return slug


def generate_unique_id(name: str, suffix_length: int = 4) -> str:
    """Generate a unique, human-readable ID from a name.

    Args:
        name: Name to convert to ID
        suffix_length: Length of unique suffix (4-8 recommended)

    Returns:
        Slug with unique suffix

    Examples:
        "Market Researcher" -> "market-researcher-a4b2"
        "Data Analyst" -> "data-analyst-7c3f"
    """
    slug = slugify(name)
    suffix = uuid.uuid4().hex[:suffix_length]
    return f"{slug}-{suffix}"


def generate_id_with_collision_check(name: str, existing_ids: set[str], suffix_length: int = 4) -> str:
    """Generate unique ID, checking against existing IDs to avoid collisions.

    Args:
        name: Name to convert to ID
        existing_ids: Set of existing IDs to check against
        suffix_length: Length of unique suffix

    Returns:
        Unique ID that doesn't collide with existing ones
    """
    # Try the base slug first (no suffix) if it's not taken
    base_slug = slugify(name)
    if base_slug not in existing_ids:
        return base_slug

    # Try with a short suffix
    for attempt in range(100):  # Prevent infinite loop
        candidate = generate_unique_id(name, suffix_length)
        if candidate not in existing_ids:
            return candidate

    # Fallback to longer suffix if we somehow get collisions
    return generate_unique_id(name, suffix_length=8)
