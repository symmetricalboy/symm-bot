"""
Main entry point for the Discord bot.
This file imports and initializes all components from their respective modules.
"""
import logging
import asyncio
import signal
import sys

# Import configuration and bot instance
from bot.config import bot, DISCORD_BOT_TOKEN, logger

# Import all modules to register their components with the bot
from bot import commands
from bot import events
from bot import utils
from bot import tasks
from bot import database

# Initialize modules that need setup
async def init_modules():
    """Initialize all modules that need setup."""
    commands.setup_commands()
    events.setup_events()
    
    # Initialize database
    logger.info("Initializing database...")
    await database.init_db()
    logger.info("Database initialization completed")

# Setup for persistent views
@bot.event
async def on_connect():
    """Set up persistent views when the bot connects."""
    logger.info("Bot connected. Setting up persistent views...")
    # This ensures the bot knows how to handle interactions with persistent views 
    # that were created before the bot restarted

# Register cleanup handlers for graceful shutdown
def register_shutdown_handlers():
    """Register signal handlers for graceful shutdown."""
    loop = asyncio.get_event_loop()
    
    async def cleanup():
        """Clean up resources before shutdown."""
        logger.info("Shutting down bot...")
        
        # Close all database connections
        await database.cleanup_db()
        
        # Close the bot connection
        if not bot.is_closed():
            await bot.close()
    
    # Register signal handlers for different platforms
    if sys.platform != "win32":
        # SIGTERM is sent when the container is stopped
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(cleanup()))
        # SIGINT is sent when pressing CTRL+C
        loop.add_signal_handler(signal.SIGINT, lambda: loop.create_task(cleanup()))

# Run the bot
if __name__ == "__main__":
    logger.info("Starting bot...")
    # Run initialization tasks
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_modules())
    
    # Register shutdown handlers
    register_shutdown_handlers()
    
    # Start the bot
    bot.run(DISCORD_BOT_TOKEN)
