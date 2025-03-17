"""
Entry point for the Discord bot.
Run this file to start the bot.
"""
from bot.main import init_modules
from bot.config import bot, DISCORD_BOT_TOKEN, logger

if __name__ == "__main__":
    logger.info("Starting symm-bot...")
    init_modules()
    bot.run(DISCORD_BOT_TOKEN) 