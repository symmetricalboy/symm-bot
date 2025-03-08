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

# Initialize modules that need setup
def init_modules():
    """Initialize all modules that need setup."""
    commands.setup_commands()
    events.setup_events()

# Run the bot
if __name__ == "__main__":
    logger.info("Starting bot...")
    init_modules()
    bot.run(DISCORD_BOT_TOKEN)
