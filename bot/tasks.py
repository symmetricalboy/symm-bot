import asyncio
import logging
import time
from asyncio import CancelledError
from .config import bot
from .utils import update_member_count_channel
from .database import get_server_config, cleanup_db

logger = logging.getLogger(__name__)

async def member_count_updater():
    """
    Background task that updates the member count channel.
    - Regular updates every 15 minutes using local counter
    - Full refresh every hour to ensure accuracy
    """
    await bot.wait_until_ready()
    
    # Keep track of the last full refresh
    last_full_refresh = 0
    
    try:
        while not bot.is_closed():
            try:
                current_time = time.time()
                
                # Determine if we need a full refresh (once per hour)
                force_refresh = (current_time - last_full_refresh) >= 3600  # 1 hour in seconds
                
                if force_refresh:
                    logger.info("Running full member count refresh")
                    last_full_refresh = current_time
                else:
                    logger.info("Running regular member count update")
                
                # Process each guild in sequence to avoid parallel database access
                for guild in bot.guilds:
                    try:
                        # Check if bot is still running before processing each guild
                        if bot.is_closed():
                            logger.info("Bot is closing, stopping member count updater")
                            return
                        
                        # Process the guild
                        await update_member_count_channel(guild, force_refresh=force_refresh)
                        
                        # Small delay between processing each guild to prevent overload
                        # This also helps ensure we're not keeping database connections open too long
                        await asyncio.sleep(2)
                    except asyncio.CancelledError:
                        logger.info(f"Member count update for {guild.name} cancelled")
                        raise  # Re-raise to handle at the task level
                    except Exception as e:
                        logger.error(f"Error updating member count for {guild.name}: {e}")
                        # Continue with other guilds even if one fails
                        continue
                
            except CancelledError:
                logger.info("Member count updater task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in member count updater task: {e}", exc_info=True)
            
            # Wait 15 minutes before the next update
            try:
                # Check every minute if the bot is still running
                for _ in range(15):  # 15 minutes = 15 iterations of 1 minute
                    if bot.is_closed():
                        logger.info("Bot is closing, stopping member count updater")
                        return
                    await asyncio.sleep(60)  # Sleep for 1 minute
            except CancelledError:
                logger.info("Member count updater task sleep cancelled")
                break
    except CancelledError:
        logger.info("Member count updater task cancelled during execution")
    finally:
        logger.info("Member count updater task finished") 