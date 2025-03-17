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
    
    # Keep track of active tasks to ensure proper cleanup
    active_tasks = set()
    
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
                
                # Clean up completed tasks
                active_tasks = {task for task in active_tasks if not task.done() and not task.cancelled()}
                    
                # Update the member count for all guilds
                for guild in bot.guilds:
                    try:
                        # Get guild configuration with a timeout
                        config = None
                        try:
                            config_task = asyncio.create_task(get_server_config(guild.id))
                            config = await asyncio.wait_for(config_task, timeout=5.0)
                        except asyncio.TimeoutError:
                            logger.error(f"Timeout getting server config in task for guild {guild.id}")
                            # Continue with defaults
                        except Exception as db_error:
                            logger.error(f"Error getting server config in task for guild {guild.id}: {db_error}")
                            # Continue with defaults
                        
                        # Check if guild has a member count channel configured
                        if config and config.get("member_count_channel_id"):
                            # Create a dedicated task for each guild's update
                            # This ensures that if one guild's update fails, it doesn't affect other guilds
                            update_task = asyncio.create_task(
                                update_member_count_channel(guild, force_refresh=force_refresh)
                            )
                            active_tasks.add(update_task)
                            
                            # Add a timeout to the task
                            try:
                                await asyncio.wait_for(update_task, timeout=30.0)
                            except asyncio.TimeoutError:
                                logger.error(f"Timeout updating member count for guild {guild.name}")
                        else:
                            # Skip guilds that don't have a member count channel configured
                            logger.debug(f"Skipping member count update for {guild.name} - no channel configured")
                    except Exception as e:
                        logger.error(f"Error updating member count for {guild.name}: {e}")
                        # Continue with other guilds even if one fails
                        continue
                    
                    # Small delay between processing each guild to prevent overload
                    await asyncio.sleep(1)
            except CancelledError:
                logger.info("Member count updater task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in member count updater task: {e}", exc_info=True)
            
            # Wait 15 minutes before the next update
            try:
                await asyncio.sleep(900)  # 15 minutes in seconds
            except CancelledError:
                logger.info("Member count updater task sleep cancelled")
                break
    except CancelledError:
        logger.info("Member count updater task cancelled during execution")
    finally:
        # Clean up any remaining tasks
        for task in active_tasks:
            if not task.done() and not task.cancelled():
                logger.info("Cancelling remaining member count update task")
                task.cancel()
        
        logger.info("Member count updater task finished") 