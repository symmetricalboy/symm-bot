"""
Main entry point for the Discord bot.
This file imports and initializes all components from their respective modules.
"""
import logging

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

# Run the bot
if __name__ == "__main__":
    logger.info("Starting bot...")
    # Run initialization tasks
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_modules())
    
    # Start the bot
    bot.run(DISCORD_BOT_TOKEN)
