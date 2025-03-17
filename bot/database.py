"""
Database module for PostgreSQL connection and operations.
"""
import os
import logging
import asyncio
import time
from typing import Optional, List, Dict, Any, Union, Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import ARRAY, TEXT

logger = logging.getLogger(__name__)

# Convert standard PostgreSQL URL to AsyncPG format
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
else:
    ASYNC_DATABASE_URL = ""
    logger.warning("No DATABASE_URL found in environment variables")

# SQLAlchemy Base class for declarative models
Base = declarative_base()

# Create async engine with proper connection handling for event loops
engine = create_async_engine(
    ASYNC_DATABASE_URL, 
    echo=False,  # Set to True for SQL query logging
    pool_size=10,  # Increased pool size
    max_overflow=20,  # Increased max overflow
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections after 30 minutes
    pool_pre_ping=True,  # Check connection validity before using it
    future=True,
    isolation_level="AUTOCOMMIT",  # Use autocommit to avoid transaction conflicts
)

# Session factory with better async handling
async_session = sessionmaker(
    bind=engine, 
    expire_on_commit=False, 
    class_=AsyncSession,
    future=True
)

# Models
class RoleMenu(Base):
    """
    Model for storing role menu configurations.
    """
    __tablename__ = "role_menus"
    
    id = sa.Column(sa.Integer, primary_key=True)
    message_id = sa.Column(sa.BigInteger, nullable=False, index=True)
    guild_id = sa.Column(sa.BigInteger, nullable=False, index=True)
    channel_id = sa.Column(sa.BigInteger, nullable=False)
    exclusive = sa.Column(sa.Boolean, nullable=False, default=False)
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())
    created_by = sa.Column(sa.BigInteger, nullable=False)
    
    def __repr__(self):
        return f"<RoleMenu id={self.id} message_id={self.message_id}>"


class RoleButton(Base):
    """
    Model for storing role button configurations.
    """
    __tablename__ = "role_buttons"
    
    id = sa.Column(sa.Integer, primary_key=True)
    menu_id = sa.Column(sa.Integer, sa.ForeignKey("role_menus.id", ondelete="CASCADE"), nullable=False)
    role_id = sa.Column(sa.BigInteger, nullable=False)
    position = sa.Column(sa.Integer, nullable=False, default=0)
    group_index = sa.Column(sa.Integer, nullable=False, default=0)  # For multiple button rows/groups
    
    def __repr__(self):
        return f"<RoleButton id={self.id} role_id={self.role_id}>"


class RoleBlock(Base):
    """
    Model for storing role blocking relationships.
    If a user has the blocking_role_id, they cannot select the blocked_role_id.
    """
    __tablename__ = "role_blocks"
    
    id = sa.Column(sa.Integer, primary_key=True)
    guild_id = sa.Column(sa.BigInteger, nullable=False, index=True)
    blocking_role_id = sa.Column(sa.BigInteger, nullable=False, index=True)
    blocked_role_id = sa.Column(sa.BigInteger, nullable=False, index=True)
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())
    
    # Add a unique constraint to prevent duplicate blocks
    __table_args__ = (
        sa.UniqueConstraint('guild_id', 'blocking_role_id', 'blocked_role_id', name='unique_role_block'),
    )
    
    def __repr__(self):
        return f"<RoleBlock id={self.id} blocking={self.blocking_role_id} blocked={self.blocked_role_id}>"


class ServerConfig(Base):
    """
    Model for storing server-specific configurations.
    Previously these were stored in environment variables.
    """
    __tablename__ = "server_configs"
    
    id = sa.Column(sa.Integer, primary_key=True)
    guild_id = sa.Column(sa.BigInteger, nullable=False, unique=True, index=True)
    
    # Channel IDs
    member_count_channel_id = sa.Column(sa.BigInteger, nullable=True)
    notifications_channel_id = sa.Column(sa.BigInteger, nullable=True)
    
    # Role IDs (using PostgreSQL's native array type)
    new_user_role_ids = sa.Column(ARRAY(sa.BigInteger), nullable=True)
    bot_role_ids = sa.Column(ARRAY(sa.BigInteger), nullable=True)
    
    # Timestamps
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())
    updated_at = sa.Column(sa.DateTime, onupdate=sa.func.now())
    
    def __repr__(self):
        return f"<ServerConfig id={self.id} guild_id={self.guild_id}>"


class ServerDocumentation(Base):
    """
    Model for storing server-specific documentation for AI help system.
    This documentation is used as context for the AI to answer user questions.
    """
    __tablename__ = "server_documentation"
    
    id = sa.Column(sa.Integer, primary_key=True)
    guild_id = sa.Column(sa.BigInteger, nullable=False, index=True)
    title = sa.Column(sa.String(255), nullable=False)
    content = sa.Column(TEXT, nullable=False)
    created_by = sa.Column(sa.BigInteger, nullable=False)
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())
    updated_at = sa.Column(sa.DateTime, onupdate=sa.func.now())
    
    def __repr__(self):
        return f"<ServerDocumentation id={self.id} title={self.title}>"


class AsyncDatabaseSession:
    """Context manager for safer database session handling."""
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        try:
            # Check if we're in a valid event loop
            try:
                loop = asyncio.get_running_loop()
                if loop.is_closed():
                    logger.warning("Event loop is closed when creating database session")
                    return None
            except RuntimeError:
                # No event loop running
                logger.warning("No event loop running when creating database session")
                return None
                
            # Create a new session
            self.session = async_session()
            return self.session
        except Exception as e:
            logger.error(f"Error creating database session: {e}")
            return None
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            try:
                # If an exception occurred, roll back any changes
                if exc_type:
                    try:
                        await self.session.rollback()
                    except Exception as e:
                        logger.error(f"Error rolling back database session: {e}")
                
                # Always close the session safely
                try:
                    # Use the same event loop that created the session
                    await self.session.close()
                except RuntimeError as e:
                    # If we get an event loop error, log it but don't crash
                    if "attached to a different loop" in str(e):
                        logger.warning(f"Event loop mismatch when closing session: {e}")
                    else:
                        logger.error(f"Runtime error closing database session: {e}")
                except Exception as e:
                    logger.error(f"Error closing database session: {e}")
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
            finally:
                # Make sure we nullify the session reference
                self.session = None

# Create a reusable session context manager
db_session = AsyncDatabaseSession

# Add function to safely close all database connections during shutdown
async def cleanup_db():
    """
    Safely close all database connections during application shutdown.
    This prevents "Event loop is closed" errors when the bot restarts.
    """
    try:
        logger.info("Closing database connections...")
        
        # Dispose of the engine to close all connections in the pool
        await engine.dispose()
        
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")

# Database operations
async def init_db():
    """Initialize the database by creating all tables."""
    # If no database URL is provided, log a warning and continue
    if not ASYNC_DATABASE_URL:
        logger.warning("No DATABASE_URL provided, skipping database initialization")
        return
    
    try:
        # Create a standalone connection for initialization to avoid loop conflicts
        async with engine.begin() as conn:
            # Create tables if they don't exist
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized successfully")
            
            # Test if tables actually exist by executing simple queries
            tables = [table.name for table in Base.metadata.tables.values()]
            logger.info(f"Initialized tables: {tables}")
            
            # Verify server_configs table exists by running a simple query
            try:
                await conn.execute(sa.text("SELECT 1 FROM server_configs LIMIT 1"))
                logger.info("Verified server_configs table exists")
            except SQLAlchemyError as e:
                logger.error(f"Verification of server_configs table failed: {e}")
                # Try to create it specifically if it doesn't exist
                await conn.execute(sa.text("""
                CREATE TABLE IF NOT EXISTS server_configs (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL UNIQUE,
                    member_count_channel_id BIGINT,
                    notifications_channel_id BIGINT,
                    new_user_role_ids BIGINT[],
                    bot_role_ids BIGINT[],
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE
                )
                """))
                logger.info("Created server_configs table manually")
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        logger.error(f"Database initialization failed: {e}")
        # Print out more detailed error information
        logger.error(f"Database URL: {ASYNC_DATABASE_URL.replace(DATABASE_URL.split('@')[0], '***')}")
        logger.error(f"Tables to create: {[table.name for table in Base.metadata.tables.values()]}")
        logger.warning("Continuing without database connection")
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        logger.warning("Continuing without database connection")


async def create_role_menu(
    message_id: int, 
    guild_id: int, 
    channel_id: int, 
    exclusive: bool, 
    created_by: int,
    role_groups: List[List[int]]
) -> Optional[int]:
    """
    Create a new role menu with buttons.
    
    Args:
        message_id: Discord message ID for this menu
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        exclusive: Whether roles are mutually exclusive
        created_by: Discord user ID who created the menu
        role_groups: Lists of role IDs grouped by rows
        
    Returns:
        The ID of the created menu, or None if failed
    """
    try:
        async with async_session() as session:
            async with session.begin():
                # Create menu
                menu = RoleMenu(
                    message_id=message_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    exclusive=exclusive,
                    created_by=created_by
                )
                session.add(menu)
                await session.flush()  # Get the ID

                # Create buttons
                for group_idx, role_ids in enumerate(role_groups):
                    for pos, role_id in enumerate(role_ids):
                        button = RoleButton(
                            menu_id=menu.id,
                            role_id=role_id,
                            position=pos,
                            group_index=group_idx
                        )
                        session.add(button)
                
                return menu.id
    except SQLAlchemyError as e:
        logger.error(f"Database error creating role menu: {e}")
        return None


async def get_role_menu_by_message(message_id: int) -> Optional[Dict[str, Any]]:
    """
    Get role menu data by Discord message ID.
    
    Args:
        message_id: Discord message ID
        
    Returns:
        Dictionary with menu data and buttons, or None if not found
    """
    try:
        async with async_session() as session:
            # Get menu
            result = await session.execute(
                select(RoleMenu).where(RoleMenu.message_id == message_id)
            )
            menu = result.scalars().first()
            
            if not menu:
                return None
                
            # Get buttons
            result = await session.execute(
                select(RoleButton)
                .where(RoleButton.menu_id == menu.id)
                .order_by(RoleButton.group_index, RoleButton.position)
            )
            buttons = result.scalars().all()
            
            # Organize buttons by group
            button_groups = {}
            for button in buttons:
                if button.group_index not in button_groups:
                    button_groups[button.group_index] = []
                button_groups[button.group_index].append({
                    "id": button.id,
                    "role_id": button.role_id,
                    "position": button.position
                })
            
            # Sort groups
            sorted_groups = [button_groups[idx] for idx in sorted(button_groups.keys())]
            
            return {
                "id": menu.id,
                "message_id": menu.message_id,
                "guild_id": menu.guild_id,
                "channel_id": menu.channel_id,
                "exclusive": menu.exclusive,
                "created_by": menu.created_by,
                "created_at": menu.created_at.isoformat() if menu.created_at else None,
                "button_groups": sorted_groups
            }
    except SQLAlchemyError as e:
        logger.error(f"Database error getting role menu: {e}")
        return None


async def get_role_menu_by_role_id(role_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
    """
    Find role menus containing a specific role.
    
    Args:
        role_id: Discord role ID
        guild_id: Discord guild ID
        
    Returns:
        Role menu data, or None if not found
    """
    try:
        async with async_session() as session:
            # Get button and associated menu
            stmt = (
                select(RoleButton, RoleMenu)
                .join(RoleMenu, RoleButton.menu_id == RoleMenu.id)
                .where(
                    (RoleButton.role_id == role_id) &
                    (RoleMenu.guild_id == guild_id)
                )
            )
            result = await session.execute(stmt)
            row = result.first()
            
            if not row:
                return None
                
            button, menu = row
            
            # Get all buttons for this menu
            result = await session.execute(
                select(RoleButton)
                .where(RoleButton.menu_id == menu.id)
                .order_by(RoleButton.position)
            )
            buttons = result.scalars().all()
            
            return {
                "id": menu.id,
                "message_id": menu.message_id,
                "guild_id": menu.guild_id,
                "exclusive": menu.exclusive,
                "button_ids": [b.role_id for b in buttons]
            }
    except SQLAlchemyError as e:
        logger.error(f"Database error getting role menu by role: {e}")
        return None


# Server configuration operations
async def get_server_config(guild_id: int) -> Optional[Dict[str, Any]]:
    """
    Get server configuration from the database.
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        Dictionary with server configuration, or None if not found
    """
    # If no database URL is provided, return None
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, returning None for server config")
        return None
        
    # Create a fresh session specifically for this operation
    session = None
    try:
        # Get a fresh session using our improved function
        session = await get_fresh_session()
        
        # If we couldn't get a session, return None
        if not session:
            logger.warning(f"Could not create database session for guild {guild_id}")
            return None
        
        # Perform the query directly with a timeout
        try:
            # Create the statement
            stmt = select(ServerConfig).where(ServerConfig.guild_id == guild_id)
            
            # Execute with timeout
            result_future = session.execute(stmt)
            result = await asyncio.wait_for(result_future, timeout=5.0)
            
            # Get the first result
            config = result.scalars().first()
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting server config for guild {guild_id}")
            return None
        except Exception as e:
            logger.error(f"Error executing query in get_server_config: {e}")
            return None
        
        if not config:
            return None
            
        # Convert to dictionary to avoid session dependency
        return {
            "id": config.id,
            "guild_id": config.guild_id,
            "member_count_channel_id": config.member_count_channel_id,
            "notifications_channel_id": config.notifications_channel_id,
            "new_user_role_ids": config.new_user_role_ids if config.new_user_role_ids else [],
            "bot_role_ids": config.bot_role_ids if config.bot_role_ids else []
        }
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        logger.error(f"Database error getting server config: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting server config: {e}")
        return None
    finally:
        # Always clean up the session
        await safe_close_session(session)


async def set_member_count_channel(guild_id: int, channel_id: int) -> bool:
    """
    Set the member count channel for a guild.
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        Whether the operation was successful
    """
    # If no database URL is provided, return failure
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, cannot set member count channel")
        return False
        
    # Use our improved session handling
    session = None
    try:
        # Get a fresh session
        session = await get_fresh_session()
        
        # If we couldn't get a session, return failure
        if not session:
            logger.warning(f"Could not create database session for setting member count channel for guild {guild_id}")
            return False
            
        # Try to find existing config
        stmt = select(ServerConfig).where(ServerConfig.guild_id == guild_id)
        result = await session.execute(stmt)
        config = result.scalars().first()
        
        if not config:
            # Create new config
            config = ServerConfig(guild_id=guild_id)
            session.add(config)
        
        # Update config
        config.member_count_channel_id = channel_id
        
        # Commit changes
        await session.commit()
        return True
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        if session:
            await session.rollback()
        logger.error(f"Database error setting member count channel: {e}")
        return False
    except Exception as e:
        if session:
            await session.rollback()
        logger.error(f"Unexpected error setting member count channel: {e}")
        return False
    finally:
        # Always clean up the session
        await safe_close_session(session)


async def set_notifications_channel(guild_id: int, channel_id: int) -> bool:
    """
    Set the notifications channel for a guild.
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        Whether the operation was successful
    """
    # If no database URL is provided, return failure
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, cannot set notifications channel")
        return False
        
    # Use our improved session handling
    session = None
    try:
        # Get a fresh session
        session = await get_fresh_session()
        
        # If we couldn't get a session, return failure
        if not session:
            logger.warning(f"Could not create database session for setting notifications channel for guild {guild_id}")
            return False
            
        # Try to find existing config
        stmt = select(ServerConfig).where(ServerConfig.guild_id == guild_id)
        result = await session.execute(stmt)
        config = result.scalars().first()
        
        if not config:
            # Create new config
            config = ServerConfig(guild_id=guild_id)
            session.add(config)
        
        # Update config
        config.notifications_channel_id = channel_id
        
        # Commit changes
        await session.commit()
        return True
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        if session:
            await session.rollback()
        logger.error(f"Database error setting notifications channel: {e}")
        return False
    except Exception as e:
        if session:
            await session.rollback()
        logger.error(f"Unexpected error setting notifications channel: {e}")
        return False
    finally:
        # Always clean up the session
        await safe_close_session(session)


async def set_new_user_roles(guild_id: int, role_ids: List[int]) -> bool:
    """
    Set the roles to assign to new users.
    
    Args:
        guild_id: Discord guild ID
        role_ids: List of role IDs to assign
        
    Returns:
        Whether the operation was successful
    """
    # If no database URL is provided, return failure
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, cannot set new user roles")
        return False
        
    # Use our improved session handling
    session = None
    try:
        # Get a fresh session
        session = await get_fresh_session()
        
        # If we couldn't get a session, return failure
        if not session:
            logger.warning(f"Could not create database session for setting new user roles for guild {guild_id}")
            return False
            
        # Try to find existing config
        stmt = select(ServerConfig).where(ServerConfig.guild_id == guild_id)
        result = await session.execute(stmt)
        config = result.scalars().first()
        
        if not config:
            # Create new config
            config = ServerConfig(guild_id=guild_id)
            session.add(config)
        
        # Update config
        config.new_user_role_ids = role_ids
        
        # Commit changes
        await session.commit()
        return True
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        if session:
            await session.rollback()
        logger.error(f"Database error setting new user roles: {e}")
        return False
    except Exception as e:
        if session:
            await session.rollback()
        logger.error(f"Unexpected error setting new user roles: {e}")
        return False
    finally:
        # Always clean up the session
        await safe_close_session(session)


async def set_bot_roles(guild_id: int, role_ids: List[int]) -> bool:
    """
    Set the bot role IDs for a guild.
    
    Args:
        guild_id: Discord guild ID
        role_ids: List of role IDs to assign to bots
        
    Returns:
        Whether the operation was successful
    """
    # Create a fresh session for this specific operation
    session = None
    try:
        session = await get_fresh_session()
        
        # Get existing config or create new one
        stmt = select(ServerConfig).where(ServerConfig.guild_id == guild_id)
        result = await session.execute(stmt)
        config = result.scalars().first()
        
        if not config:
            # Create new config
            config = ServerConfig(guild_id=guild_id)
            session.add(config)
        
        # Update config
        config.bot_role_ids = role_ids
        
        # Commit changes
        await session.commit()
        return True
    except SQLAlchemyError as e:
        if session:
            await session.rollback()
        logger.error(f"Database error setting bot roles: {e}")
        return False
    finally:
        await safe_close_session(session)


async def add_role_block(guild_id: int, blocking_role_id: int, blocked_role_id: int) -> bool:
    """
    Add a role blocking relationship.
    
    Args:
        guild_id: Discord guild ID
        blocking_role_id: The role ID that blocks
        blocked_role_id: The role ID that is blocked
        
    Returns:
        Whether the operation was successful
    """
    # If no database URL is provided, return failure
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, cannot add role block")
        return False
        
    # Use our improved session handling
    session = None
    try:
        # Get a fresh session
        session = await get_fresh_session()
        
        # If we couldn't get a session, return failure
        if not session:
            logger.warning(f"Could not create database session for adding role block for guild {guild_id}")
            return False
            
        # Check if the block already exists
        stmt = select(RoleBlock).where(
            (RoleBlock.guild_id == guild_id) &
            (RoleBlock.blocking_role_id == blocking_role_id) &
            (RoleBlock.blocked_role_id == blocked_role_id)
        )
        result = await session.execute(stmt)
        existing_block = result.scalars().first()
        
        if not existing_block:
            # Create new block
            block = RoleBlock(
                guild_id=guild_id,
                blocking_role_id=blocking_role_id,
                blocked_role_id=blocked_role_id
            )
            session.add(block)
        
        # Commit changes
        await session.commit()
        return True
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        if session:
            await session.rollback()
        logger.error(f"Database error adding role block: {e}")
        return False
    except Exception as e:
        if session:
            await session.rollback()
        logger.error(f"Unexpected error adding role block: {e}")
        return False
    finally:
        # Always clean up the session
        await safe_close_session(session)


async def remove_role_block(guild_id: int, blocking_role_id: int, blocked_role_id: int) -> bool:
    """
    Remove a role blocking relationship.
    
    Args:
        guild_id: Discord guild ID
        blocking_role_id: Role ID that blocks
        blocked_role_id: Role ID that is blocked
        
    Returns:
        Whether the operation was successful
    """
    # If no database URL is provided, return failure
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, cannot remove role block")
        return False
        
    # Use our improved session handling
    session = None
    try:
        # Get a fresh session
        session = await get_fresh_session()
        
        # If we couldn't get a session, return failure
        if not session:
            logger.warning(f"Could not create database session for removing role block for guild {guild_id}")
            return False
            
        # Delete the block
        stmt = sa.delete(RoleBlock).where(
            (RoleBlock.guild_id == guild_id) &
            (RoleBlock.blocking_role_id == blocking_role_id) &
            (RoleBlock.blocked_role_id == blocked_role_id)
        )
        await session.execute(stmt)
        
        # Commit changes
        await session.commit()
        return True
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        if session:
            await session.rollback()
        logger.error(f"Database error removing role block: {e}")
        return False
    except Exception as e:
        if session:
            await session.rollback()
        logger.error(f"Unexpected error removing role block: {e}")
        return False
    finally:
        # Always clean up the session
        await safe_close_session(session)


async def get_blocked_roles(guild_id: int, user_roles: List[int]) -> List[int]:
    """
    Get a list of role IDs that are blocked for a user based on their current roles.
    
    Args:
        guild_id: Discord guild ID
        user_roles: List of role IDs that the user has
        
    Returns:
        List of role IDs that are blocked for the user
    """
    try:
        async with async_session() as session:
            # Find all blocks where the blocking role is in the user's roles
            blocked_roles = []
            
            for role_id in user_roles:
                # For each role the user has, find the roles it blocks
                result = await session.execute(
                    select(RoleBlock.blocked_role_id).where(
                        (RoleBlock.guild_id == guild_id) &
                        (RoleBlock.blocking_role_id == role_id)
                    )
                )
                
                # Add the blocked roles to the list
                for row in result.scalars().all():
                    if row not in blocked_roles:
                        blocked_roles.append(row)
            
            return blocked_roles
    except SQLAlchemyError as e:
        logger.error(f"Database error getting blocked roles: {e}")
        return []


async def get_blocking_role(guild_id: int, user_roles: List[int], role_id: int) -> Optional[int]:
    """
    Find which of the user's roles is blocking a specific role.
    
    Args:
        guild_id: Discord guild ID
        user_roles: List of role IDs that the user has
        role_id: Role ID to check if it's blocked
        
    Returns:
        The role ID that is blocking, or None if not blocked
    """
    try:
        async with async_session() as session:
            for blocking_role_id in user_roles:
                # Check if this role blocks the target role
                result = await session.execute(
                    select(RoleBlock).where(
                        (RoleBlock.guild_id == guild_id) &
                        (RoleBlock.blocking_role_id == blocking_role_id) &
                        (RoleBlock.blocked_role_id == role_id)
                    )
                )
                
                if result.scalars().first():
                    return blocking_role_id
            
            # No blocking role found
            return None
    except SQLAlchemyError as e:
        logger.error(f"Database error getting blocking role: {e}")
        return None


async def get_role_blocks(guild_id: int) -> List[Dict[str, int]]:
    """
    Get all role blocking relationships for a guild.
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        List of dictionaries containing blocking_role_id and blocked_role_id
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(RoleBlock).where(RoleBlock.guild_id == guild_id)
            )
            
            blocks = []
            for block in result.scalars().all():
                blocks.append({
                    "id": block.id,
                    "blocking_role_id": block.blocking_role_id,
                    "blocked_role_id": block.blocked_role_id
                })
            
            return blocks
    except SQLAlchemyError as e:
        logger.error(f"Database error getting role blocks: {e}")
        return []


# Server documentation operations
async def add_server_documentation(
    guild_id: int,
    title: str,
    content: str,
    created_by: int
) -> Optional[int]:
    """
    Add or update server documentation.
    
    Args:
        guild_id: Discord guild ID
        title: Title of the documentation
        content: Content of the documentation
        created_by: Discord user ID who created the documentation
        
    Returns:
        The ID of the created/updated documentation, or None if failed
    """
    try:
        async with async_session() as session:
            async with session.begin():
                # Check if a document with this title already exists
                result = await session.execute(
                    select(ServerDocumentation).where(
                        (ServerDocumentation.guild_id == guild_id) &
                        (ServerDocumentation.title == title)
                    )
                )
                existing_doc = result.scalars().first()
                
                if existing_doc:
                    # Update existing document
                    existing_doc.content = content
                    existing_doc.created_by = created_by
                    doc_id = existing_doc.id
                else:
                    # Create new document
                    doc = ServerDocumentation(
                        guild_id=guild_id,
                        title=title,
                        content=content,
                        created_by=created_by
                    )
                    session.add(doc)
                    await session.flush()
                    doc_id = doc.id
                
                return doc_id
    except SQLAlchemyError as e:
        logger.error(f"Database error adding server documentation: {e}")
        return None


async def delete_server_documentation(guild_id: int, title: str) -> bool:
    """
    Delete server documentation.
    
    Args:
        guild_id: Discord guild ID
        title: Title of the documentation to delete
        
    Returns:
        Whether the operation was successful
    """
    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    sa.delete(ServerDocumentation).where(
                        (ServerDocumentation.guild_id == guild_id) &
                        (ServerDocumentation.title == title)
                    )
                )
                return True
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting server documentation: {e}")
        return False


async def get_server_documentation(guild_id: int, title: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get server documentation.
    
    Args:
        guild_id: Discord guild ID
        title: Optional title to filter by
        
    Returns:
        List of documentation entries
    """
    # If no database URL is provided, return empty list
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, returning empty list for server documentation")
        return []
        
    # Create a fresh session specifically for this operation
    session = None
    try:
        # Get a fresh session using our improved function
        session = await get_fresh_session()
        
        # If we couldn't get a session, return empty list
        if not session:
            logger.warning(f"Could not create database session for getting server documentation for guild {guild_id}")
            return []
        
        # Perform the query directly with a timeout
        try:
            if title:
                # Get specific document
                stmt = select(ServerDocumentation).where(
                    (ServerDocumentation.guild_id == guild_id) &
                    (ServerDocumentation.title == title)
                )
                
                # Execute with timeout
                result_future = session.execute(stmt)
                result = await asyncio.wait_for(result_future, timeout=5.0)
                
                doc = result.scalars().first()
                
                if not doc:
                    return []
                    
                return [{
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content,
                    "created_by": doc.created_by,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
                }]
            else:
                # Get all documents for this guild
                stmt = select(ServerDocumentation).where(
                    ServerDocumentation.guild_id == guild_id
                ).order_by(ServerDocumentation.title)
                
                # Execute with timeout
                result_future = session.execute(stmt)
                result = await asyncio.wait_for(result_future, timeout=5.0)
                
                docs = result.scalars().all()
                
                return [{
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content,
                    "created_by": doc.created_by,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
                } for doc in docs]
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting server documentation for guild {guild_id}")
            return []
        except Exception as e:
            logger.error(f"Error executing query in get_server_documentation: {e}")
            return []
    except (SQLAlchemyError, ConnectionRefusedError) as e:
        logger.error(f"Database error getting server documentation: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error getting server documentation: {e}")
        return []
    finally:
        # Always clean up the session
        await safe_close_session(session)


async def get_all_server_documentation_content(guild_id: int) -> str:
    """
    Get all server documentation content concatenated into a single string.
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        Concatenated documentation content
    """
    try:
        # Get documentation with properly managed session
        docs = await get_server_documentation(guild_id)
        
        if not docs:
            return ""
        
        content_parts = []
        for doc in docs:
            content_parts.append(f"# {doc['title']}\n\n{doc['content']}")
        
        return "\n\n---\n\n".join(content_parts)
    except Exception as e:
        logger.error(f"Error getting all server documentation content: {e}")
        return ""


async def get_fresh_session():
    """
    Get a fresh database session that will work reliably across different async tasks.
    This function should be used instead of directly creating a session or using db_session.
    
    Returns:
        A fresh SQLAlchemy AsyncSession
    """
    # If there's no database URL, return None
    if not ASYNC_DATABASE_URL:
        logger.debug("No DATABASE_URL provided, can't create session")
        return None
        
    try:
        # Check if we're in a valid event loop
        try:
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                logger.warning("Event loop is closed when creating database session")
                return None
        except RuntimeError:
            # No event loop running
            logger.warning("No event loop running when creating database session")
            return None
            
        # Create a new session bound to the current event loop
        # Use engine that is bound to this specific loop
        local_engine = create_async_engine(
            ASYNC_DATABASE_URL, 
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            future=True,
            isolation_level="AUTOCOMMIT",
        )
        
        # Create session factory bound to this engine
        local_session_maker = sessionmaker(
            bind=local_engine, 
            expire_on_commit=False, 
            class_=AsyncSession,
            future=True
        )
        
        # Create a new session for this specific operation
        session = local_session_maker()
        return session
    except Exception as e:
        logger.error(f"Error creating database session: {e}")
        return None

async def safe_close_session(session):
    """
    Safely close a database session, handling any exceptions.
    
    Args:
        session: The session to close
    """
    if not session:
        return
        
    try:
        # Check if we're in a valid event loop
        try:
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                logger.warning("Event loop is closed when closing database session")
                return
        except RuntimeError:
            # No event loop running
            logger.warning("No event loop running when closing database session")
            return
        
        # Get the engine from this session
        engine = session.bind
        
        # Close the session with timeout
        try:
            await asyncio.wait_for(session.close(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("Timeout closing database session")
        except Exception as e:
            logger.error(f"Error closing database session: {e}")
        
        # Dispose the engine if it was created locally
        # We compare to the global engine variable directly
        if engine is not None and engine is not globals().get('engine'):
            try:
                await asyncio.wait_for(engine.dispose(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Timeout disposing database engine")
            except Exception as e:
                logger.error(f"Error disposing database engine: {e}")
    except Exception as e:
        logger.error(f"Unexpected error closing database session: {e}")

async def safe_db_operation(operation_func, *args, **kwargs):
    """
    Safely execute a database operation with proper error handling for event loop issues.
    
    Args:
        operation_func: The database function to call
        *args, **kwargs: Arguments to pass to the function
        
    Returns:
        The result of the operation, or None if an error occurred
    """
    try:
        return await operation_func(*args, **kwargs)
    except RuntimeError as e:
        if "attached to a different loop" in str(e):
            logger.warning(f"Event loop mismatch in database operation: {e}")
            # In a production environment, you could implement a retry mechanism here
            # For now, we'll just return None to avoid crashing
            return None
        else:
            logger.error(f"Runtime error in database operation: {e}")
            return None
    except Exception as e:
        logger.error(f"Error in database operation: {e}")
        return None 