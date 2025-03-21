"""
Utility functions for the Discord bot.
This module provides helper functions for various bot operations,
particularly focused on member count handling and role management.
"""
import asyncio
import logging
import disnake
from .config import bot
from .database import get_server_config

logger = logging.getLogger(__name__)

# Dictionary to store human member counts per guild
# Format: {guild_id: {"human_count": count, "last_verified": timestamp}}
member_counts = {}

async def get_roles_by_ids(guild: disnake.Guild, role_ids: list[int]) -> list[disnake.Role]:
    """
    Get a list of role objects from a list of role IDs.
    
    Args:
        guild: The guild to get roles from
        role_ids: List of role IDs to fetch
        
    Returns:
        List of role objects
    """
    roles = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            roles.append(role)
        else:
            logger.error(f"Role with ID {role_id} not found in guild {guild.name}")
    return roles

async def get_human_member_count(guild: disnake.Guild, force_refresh: bool = False) -> int:
    """
    Get the human member count for a guild, either from cache or by counting.
    
    Args:
        guild: The guild to get the count for
        force_refresh: Whether to force a full count refresh
    
    Returns:
        The number of human members in the guild
    """
    guild_id = guild.id
    
    # If we need to force a refresh or don't have a count for this guild yet
    if force_refresh or guild_id not in member_counts:
        try:
            # Try to get the most up-to-date member list
            await guild.chunk()  # Ensure all members are cached
            human_count = sum(1 for member in guild.members if not member.bot)
            logger.info(f"Counted {human_count} human members out of {guild.member_count} total members in {guild.name}")
            
            # Save the count to our cache
            from time import time
            member_counts[guild_id] = {"human_count": human_count, "last_verified": time()}
            
            return human_count
            
        except Exception as e:
            # If chunking fails, try to use the approximate member count
            logger.warning(f"Could not fetch complete member list: {e}, using approximation")
            try:
                # Fallback to approximate count and estimate
                updated_guild = await bot.fetch_guild(guild.id, with_counts=True)
                # We can't get exact bot count in this case, so we might need to estimate
                # Let's assume current bot ratio is similar to what we have in cache
                if guild.member_count > 0:
                    cached_bot_ratio = sum(1 for m in guild.members if m.bot) / len(guild.members)
                    estimated_bot_count = updated_guild.approximate_member_count * cached_bot_ratio
                    human_count = int(updated_guild.approximate_member_count - estimated_bot_count)
                else:
                    # If we have no cached members, just use the approximate count
                    human_count = updated_guild.approximate_member_count
                logger.info(f"Estimated {human_count} human members in {guild.name} using approximate count")
                
                # Save the count to our cache
                from time import time
                member_counts[guild_id] = {"human_count": human_count, "last_verified": time()}
                
                return human_count
                
            except Exception as e2:
                # If all else fails, just use the cached members and filter bots
                logger.warning(f"Could not fetch updated guild info: {e2}, using cached members only")
                human_count = sum(1 for member in guild.members if not member.bot)
                
                # Save the count to our cache
                from time import time
                member_counts[guild_id] = {"human_count": human_count, "last_verified": time()}
                
                return human_count
    
    # If we already have a count, just return it
    return member_counts[guild_id]["human_count"]

def increment_member_count(guild_id: int) -> None:
    """
    Increment the human member count for a guild by 1.
    
    Args:
        guild_id: The ID of the guild to increment the count for
    """
    if guild_id in member_counts:
        member_counts[guild_id]["human_count"] += 1
        logger.info(f"Incremented human member count for guild {guild_id} to {member_counts[guild_id]['human_count']}")
    # If we don't have a count yet, we'll initialize it on the next update

def decrement_member_count(guild_id: int) -> None:
    """
    Decrement the human member count for a guild by 1.
    
    Args:
        guild_id: The ID of the guild to decrement the count for
    """
    if guild_id in member_counts:
        member_counts[guild_id]["human_count"] -= 1
        logger.info(f"Decremented human member count for guild {guild_id} to {member_counts[guild_id]['human_count']}")
    # If we don't have a count yet, we'll initialize it on the next update

async def update_member_count_channel(guild: disnake.Guild, force_refresh: bool = False) -> bool:
    """
    Updates the member count channel name to show the total number of human members in the server.
    Excludes bots from the count.
    
    Args:
        guild: The guild to update the member count channel for
        force_refresh: Whether to force a full count refresh even if we have cached data
        
    Returns:
        True if the update was successful, False otherwise
    """
    try:
        # Check if event loop is closed
        try:
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                logger.warning(f"Event loop is closed when updating member count for guild {guild.name}")
                return False
        except RuntimeError:
            # No event loop running
            logger.warning(f"No event loop running when updating member count for guild {guild.name}")
            return False
        
        # Get the member count channel ID from the database
        server_config = None
        member_count_channel_id = None
        
        try:
            # Use a local task for database operations to ensure it uses the current event loop
            async def get_config():
                return await get_server_config(guild.id)
                
            # Get the server config with a timeout
            server_config = await asyncio.wait_for(get_config(), timeout=10.0)
            
            if server_config:
                member_count_channel_id = server_config.get("member_count_channel_id")
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting server config for guild {guild.id}")
            return False
        except Exception as db_error:
            logger.error(f"Error getting server config for guild {guild.id}: {db_error}")
            return False
        
        # If we don't have a channel ID, log and return
        if not member_count_channel_id:
            logger.debug(f"No member count channel configured for guild {guild.name}")
            return False
        
        channel = guild.get_channel(member_count_channel_id)
        if not channel:
            logger.error(f"Member count channel with ID {member_count_channel_id} not found in guild {guild.name}")
            return False
        
        # Get the human member count with a timeout
        try:
            # Use a local task for member count to ensure it uses the current event loop
            async def count_members():
                return await get_human_member_count(guild, force_refresh)
                
            human_count = await asyncio.wait_for(count_members(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting human member count for guild {guild.name}")
            return False
        except Exception as e:
            logger.error(f"Error getting human member count for guild {guild.name}: {e}")
            return False
        
        # Ensure the bot has the permissions to update the channel
        bot_member = guild.get_member(bot.user.id)
        if not bot_member:
            logger.error(f"Bot member not found in guild {guild.name}")
            return False
            
        permissions = channel.permissions_for(bot_member)
        if not permissions.manage_channels:
            logger.warning(f"Bot doesn't have permission to manage channels in {guild.name}")
            return False
            
        # Update the channel name
        new_name = f"Members: {human_count}"
        
        if channel.name != new_name:
            try:
                # Use a local task for channel edit to ensure it uses the current event loop
                async def edit_channel():
                    await channel.edit(name=new_name)
                    
                await asyncio.wait_for(edit_channel(), timeout=10.0)
                logger.info(f"Updated member count channel in {guild.name} to '{new_name}'")
                return True
            except asyncio.TimeoutError:
                logger.error(f"Timeout updating member count channel in {guild.name}")
                return False
            except Exception as e:
                logger.error(f"Error updating member count channel in {guild.name}: {e}")
                return False
        else:
            logger.info(f"Member count channel in {guild.name} already up to date: '{new_name}'")
            return True
    except Exception as e:
        logger.error(f"Unexpected error in update_member_count_channel for {guild.name}: {e}", exc_info=True)
        return False 