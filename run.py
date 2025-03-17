"""
Entry point for the Discord bot.
Run this file to start the bot.
"""
import asyncio
import signal
import sys
from bot.main import init_modules, register_shutdown_handlers
from bot.config import bot, DISCORD_BOT_TOKEN, logger
from bot.database import cleanup_db

async def shutdown():
    """Clean up resources before shutdown."""
    logger.info("Shutting down bot from run.py...")
    
    # Close all database connections
    await cleanup_db()
    
    # Close the bot connection
    if not bot.is_closed():
        await bot.close()

if __name__ == "__main__":
    logger.info("Starting symm-bot...")
    
    # Setup event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Run initialization tasks
    loop.run_until_complete(init_modules())
    
    # Register shutdown handlers for graceful shutdown
    register_shutdown_handlers()
    
    # Handle CTRL+C and container stop signals
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        # Ensure proper cleanup on keyboard interrupt
        logger.info("Keyboard interrupt received, shutting down...")
        loop.run_until_complete(shutdown())
    finally:
        # Make sure everything is properly closed
        pending = asyncio.all_tasks(loop=loop)
        if pending:
            logger.info(f"Cancelling {len(pending)} pending tasks...")
            for task in pending:
                task.cancel()
            
            # Wait for all tasks to be cancelled
            try:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except asyncio.CancelledError:
                pass
            
        loop.close()
        logger.info("Shutdown complete") 