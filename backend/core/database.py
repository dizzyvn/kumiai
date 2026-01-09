"""Database connection and session management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from .config import settings

# Create async engine with SQLite-specific optimizations
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={
        "timeout": 30,  # Increase timeout to 30 seconds
        "check_same_thread": False,  # Allow multiple threads
    },
    pool_pre_ping=True,  # Verify connections before using
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db():
    """Dependency for getting database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables and enable WAL mode."""
    async with engine.begin() as conn:
        # Enable WAL mode for better concurrency
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=30000"))  # 30 seconds
        await conn.run_sync(Base.metadata.create_all)

        # Migration: Add project_id column to sessions table if it doesn't exist
        try:
            # Check if project_id column exists
            result = await conn.execute(text("PRAGMA table_info(sessions)"))
            columns = [row[1] for row in result.fetchall()]

            if 'project_id' not in columns:
                print("⚙️  Running migration: Adding project_id column to sessions table...")
                # Add the column (SQLite doesn't support ALTER TABLE ADD COLUMN with foreign keys directly)
                await conn.execute(text("ALTER TABLE sessions ADD COLUMN project_id TEXT DEFAULT 'default'"))
                print("✓ Migration complete: project_id column added")
        except Exception as e:
            print(f"⚠️  Migration note: {e}")

        # Migration: Update characters table to hybrid architecture
        # (SQLite doesn't support DROP COLUMN directly, so we recreate tables)
        try:
            result = await conn.execute(text("PRAGMA table_info(characters)"))
            columns = [row[1] for row in result.fetchall()]

            # Check if we have the new hybrid architecture columns
            required_columns = {'allowed_tools', 'allowed_mcp_servers', 'allowed_skills', 'color'}
            has_new_schema = all(col in columns for col in required_columns)

            if not has_new_schema:
                print("⚙️  Running migration: Updating characters table to hybrid architecture...")

                # Create new table with hybrid architecture schema
                await conn.execute(text("""
                    CREATE TABLE characters_new (
                        id TEXT PRIMARY KEY,
                        allowed_tools TEXT,
                        allowed_mcp_servers TEXT,
                        allowed_skills TEXT,
                        avatar TEXT,
                        color TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME
                    )
                """))

                # Copy data from old table (only id and avatar if they exist)
                if 'avatar' in columns:
                    await conn.execute(text("""
                        INSERT INTO characters_new (id, avatar)
                        SELECT id, avatar FROM characters
                    """))
                else:
                    await conn.execute(text("""
                        INSERT INTO characters_new (id)
                        SELECT id FROM characters
                    """))

                # Drop old table and rename new one
                await conn.execute(text("DROP TABLE characters"))
                await conn.execute(text("ALTER TABLE characters_new RENAME TO characters"))

                print("✓ Migration complete: Characters table updated to hybrid architecture")

            # Migration: Drop skills table (DISABLED - keeping skills table for now)
            # result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='skills'"))
            # if result.fetchone():
            #     print("⚙️  Running migration: Dropping skills table (skills are now pure filesystem)...")
            #     await conn.execute(text("DROP TABLE skills"))
            #     print("✓ Migration complete: Skills table dropped")

        except Exception as e:
            print(f"⚠️  Migration note: {e}")

        # Migration: Create session_messages table if it doesn't exist
        try:
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='session_messages'"))
            if not result.fetchone():
                print("⚙️  Running migration: Creating session_messages table...")
                await conn.execute(text("""
                    CREATE TABLE session_messages (
                        id TEXT PRIMARY KEY,
                        instance_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        agent_name TEXT,
                        tool_name TEXT,
                        tool_args TEXT,
                        sender_role TEXT,
                        sender_name TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        cost_usd REAL,
                        is_streaming BOOLEAN DEFAULT 0,
                        FOREIGN KEY (instance_id) REFERENCES sessions(instance_id) ON DELETE CASCADE
                    )
                """))
                await conn.execute(text("CREATE INDEX idx_instance_timestamp ON session_messages(instance_id, timestamp)"))
                await conn.execute(text("CREATE INDEX idx_instance_role ON session_messages(instance_id, role)"))
                await conn.execute(text("CREATE INDEX idx_session_messages_sender_role ON session_messages(instance_id, sender_role)"))
                print("✓ Migration complete: session_messages table created")
            else:
                # Add sender attribution columns if they don't exist
                result = await conn.execute(text("PRAGMA table_info(session_messages)"))
                columns = [row[1] for row in result.fetchall()]

                if 'sender_role' not in columns:
                    print("⚙️  Running migration: Adding sender attribution columns...")
                    await conn.execute(text("ALTER TABLE session_messages ADD COLUMN sender_role TEXT"))
                    await conn.execute(text("ALTER TABLE session_messages ADD COLUMN sender_name TEXT"))
                    await conn.execute(text("ALTER TABLE session_messages ADD COLUMN sender_id TEXT"))
                    await conn.execute(text("UPDATE session_messages SET sender_role = 'user' WHERE role = 'user' AND sender_role IS NULL"))
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_session_messages_sender_role ON session_messages(instance_id, sender_role)"))
                    print("✓ Migration complete: Sender attribution columns added")
                elif 'sender_id' not in columns:
                    print("⚙️  Running migration: Adding sender_id column...")
                    await conn.execute(text("ALTER TABLE session_messages ADD COLUMN sender_id TEXT"))
                    print("✓ Migration complete: sender_id column added")
        except Exception as e:
            print(f"⚠️  Migration note: {e}")

        # Migration: Add pm_instance_id column to projects table
        try:
            result = await conn.execute(text("PRAGMA table_info(projects)"))
            columns = [row[1] for row in result.fetchall()]

            if 'pm_instance_id' not in columns:
                print("⚙️  Running migration: Adding pm_instance_id column to projects table...")
                await conn.execute(text("ALTER TABLE projects ADD COLUMN pm_instance_id TEXT"))

                # Backfill existing projects with their PM instance IDs (use most recent PM)
                print("⚙️  Backfilling pm_instance_id for existing projects...")
                result = await conn.execute(text("""
                    UPDATE projects
                    SET pm_instance_id = (
                        SELECT instance_id
                        FROM sessions
                        WHERE sessions.project_id = projects.id
                            AND sessions.role = 'pm'
                            AND sessions.status != 'cancelled'
                        ORDER BY sessions.started_at DESC
                        LIMIT 1
                    )
                    WHERE EXISTS (
                        SELECT 1
                        FROM sessions
                        WHERE sessions.project_id = projects.id
                            AND sessions.role = 'pm'
                            AND sessions.status != 'cancelled'
                    )
                """))
                backfilled_count = result.rowcount
                print(f"✓ Migration complete: pm_instance_id column added and {backfilled_count} projects backfilled")
        except Exception as e:
            print(f"⚠️  Migration note: {e}")

        # Migration: Add tool_use_id and is_error columns to session_messages table
        try:
            result = await conn.execute(text("PRAGMA table_info(session_messages)"))
            columns = [row[1] for row in result.fetchall()]

            if 'tool_use_id' not in columns:
                print("⚙️  Running migration: Adding tool_use_id and is_error columns to session_messages table...")
                await conn.execute(text("ALTER TABLE session_messages ADD COLUMN tool_use_id TEXT"))
                await conn.execute(text("ALTER TABLE session_messages ADD COLUMN is_error BOOLEAN DEFAULT 0"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tool_use_id ON session_messages(tool_use_id)"))
                print("✓ Migration complete: tool_use_id and is_error columns added")
        except Exception as e:
            print(f"⚠️  Migration note: {e}")

        # Migration: Add sequence column to session_messages table
        try:
            result = await conn.execute(text("PRAGMA table_info(session_messages)"))
            columns = [row[1] for row in result.fetchall()]

            if 'sequence' not in columns:
                print("⚙️  Running migration: Adding sequence column to session_messages table...")
                await conn.execute(text("ALTER TABLE session_messages ADD COLUMN sequence INTEGER DEFAULT 0"))
                print("✓ Migration complete: sequence column added")
        except Exception as e:
            print(f"⚠️  Migration note: {e}")


    # Create default project if it doesn't exist
    from ..models.database import Project, DEFAULT_PROJECT_ID
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Project).where(Project.id == DEFAULT_PROJECT_ID)
        )
        default_project = result.scalar_one_or_none()

        if not default_project:
            default_project = Project(
                id=DEFAULT_PROJECT_ID,
                name="Default Project",
                description="Default project for sessions not assigned to a specific project",
                color="#6B7280",
            )
            session.add(default_project)
            await session.commit()
            print(f"✓ Created default project (ID: {DEFAULT_PROJECT_ID})")
        else:
            print(f"✓ Default project already exists (ID: {DEFAULT_PROJECT_ID})")
