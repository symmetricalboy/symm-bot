import asyncio
import logging
import time
from .config import bot
from .utils import update_member_count_channel
from .database import get_server_config

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
    
    while not bot.is_closed():
        current_time = time.time()
        
        # Determine if we need a full refresh (once per hour)
        force_refresh = (current_time - last_full_refresh) >= 3600  # 1 hour in seconds
        
        if force_refresh:
            logger.info("Running full member count refresh")
            last_full_refresh = current_time
        else:
            logger.info("Running regular member count update")
            
        # Update the member count for all guilds
        for guild in bot.guilds:
            # Check if guild has a member count channel configured
            config = await get_server_config(guild.id)
            if config and config.get("member_count_channel_id"):
                await update_member_count_channel(guild, force_refresh=force_refresh)
            else:
                # Skip guilds that don't have a member count channel configured
                logger.debug(f"Skipping member count update for {guild.name} - no channel configured")
        
        # Wait 15 minutes before the next update
        await asyncio.sleep(900)  # 15 minutes in seconds 