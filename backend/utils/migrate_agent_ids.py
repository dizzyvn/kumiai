"""Utility script to migrate agents from UUID-based IDs to human-readable slugs.

Usage:
    python -m backend.utils.migrate_agent_ids

This script will:
1. Scan character_library for agents with UUID-based IDs
2. Generate readable slugs from their names
3. Rename directories and update database records
"""
import asyncio
import re
import shutil
from pathlib import Path

from ..core.config import settings
from ..core.database import get_db
from ..models.database import Character
from ..utils.character_file import CharacterFile
from ..utils.slug import slugify, generate_unique_id
from sqlalchemy import select


def is_uuid(text: str) -> bool:
    """Check if a string looks like a UUID."""
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return bool(re.match(uuid_pattern, text, re.IGNORECASE))


async def migrate_agents():
    """Migrate all agents with UUID IDs to readable slugs."""
    print("🔍 Scanning for agents with UUID-based IDs...")

    characters_dir = settings.characters_dir
    if not characters_dir.exists():
        print("❌ Characters directory not found")
        return

    # Get database session
    db_gen = get_db()
    db = await anext(db_gen)

    try:
        migrations = []

        # Scan for agents with UUID IDs
        for char_dir in characters_dir.iterdir():
            if not char_dir.is_dir() or char_dir.name.startswith('_'):
                continue

            char_id = char_dir.name

            # Check if it's a UUID
            if not is_uuid(char_id):
                print(f"✅ {char_id} - Already has readable ID")
                continue

            # Load agent.md to get the name
            agent_file = char_dir / "agent.md"
            if not agent_file.exists():
                print(f"⚠️  {char_id} - No agent.md found, skipping")
                continue

            try:
                char_file = CharacterFile.from_file(agent_file)
                new_id = slugify(char_file.name)

                # Check for collisions
                existing_ids = {d.name for d in characters_dir.iterdir() if d.is_dir()}
                if new_id in existing_ids:
                    # Add suffix if collision detected
                    new_id = generate_unique_id(char_file.name, suffix_length=4)

                migrations.append({
                    'old_id': char_id,
                    'new_id': new_id,
                    'name': char_file.name,
                    'old_path': char_dir,
                    'new_path': characters_dir / new_id,
                })

                print(f"📋 {char_file.name}")
                print(f"   {char_id} → {new_id}")

            except Exception as e:
                print(f"❌ {char_id} - Error reading: {e}")
                continue

        if not migrations:
            print("\n✨ No migrations needed - all agents have readable IDs!")
            return

        # Confirm with user
        print(f"\n📊 Found {len(migrations)} agent(s) to migrate")
        response = input("\nProceed with migration? (yes/no): ")

        if response.lower() not in ['yes', 'y']:
            print("❌ Migration cancelled")
            return

        # Perform migrations
        print("\n🚀 Starting migration...\n")

        for migration in migrations:
            old_id = migration['old_id']
            new_id = migration['new_id']
            old_path = migration['old_path']
            new_path = migration['new_path']

            try:
                # Rename directory
                shutil.move(str(old_path), str(new_path))
                print(f"✅ Renamed directory: {old_id} → {new_id}")

                # Update database record
                result = await db.execute(
                    select(Character).where(Character.id == old_id)
                )
                char = result.scalar_one_or_none()

                if char:
                    # Delete old record
                    await db.delete(char)
                    await db.flush()

                    # Create new record with new ID
                    new_char = Character(
                        id=new_id,
                        avatar=char.avatar,
                        allowed_tools=char.allowed_tools,
                        allowed_mcp_servers=char.allowed_mcp_servers,
                        allowed_skills=char.allowed_skills,
                    )
                    db.add(new_char)
                    await db.flush()

                    print(f"✅ Updated database: {old_id} → {new_id}")

            except Exception as e:
                print(f"❌ Failed to migrate {old_id}: {e}")
                # Try to rollback directory rename
                if new_path.exists() and not old_path.exists():
                    shutil.move(str(new_path), str(old_path))
                continue

        await db.commit()
        print(f"\n✨ Migration complete! Migrated {len(migrations)} agent(s)")

    except Exception as e:
        await db.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(migrate_agents())
