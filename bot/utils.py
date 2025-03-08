import disnake
import logging
from .config import MEMBER_COUNT_CHANNEL_ID, bot

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

async def get_human_member_count(guild: disnake.Guild, force_refresh=False):
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

def increment_member_count(guild_id):
    """
    Increment the human member count for a guild by 1.
    
    Args:
        guild_id: The ID of the guild to increment the count for
    """
    if guild_id in member_counts:
        member_counts[guild_id]["human_count"] += 1
        logger.info(f"Incremented human member count for guild {guild_id} to {member_counts[guild_id]['human_count']}")
    # If we don't have a count yet, we'll initialize it on the next update

def decrement_member_count(guild_id):
    """
    Decrement the human member count for a guild by 1.
    
    Args:
        guild_id: The ID of the guild to decrement the count for
    """
    if guild_id in member_counts:
        member_counts[guild_id]["human_count"] -= 1
        logger.info(f"Decremented human member count for guild {guild_id} to {member_counts[guild_id]['human_count']}")
    # If we don't have a count yet, we'll initialize it on the next update

async def update_member_count_channel(guild: disnake.Guild, force_refresh=False):
    """
    Updates the member count channel name to show the total number of human members in the server.
    Excludes bots from the count.
    
    Args:
        guild: The guild to update the member count for
        force_refresh: Whether to force a full count refresh
    """
    try:
        channel = guild.get_channel(MEMBER_COUNT_CHANNEL_ID)
        if not channel:
            logger.error(f"Member count channel with ID {MEMBER_COUNT_CHANNEL_ID} not found")
            return
        
        # Get the human member count
        human_count = await get_human_member_count(guild, force_refresh)
            
        # Format: "Members: 123"
        new_name = f"Members: {human_count}"
        
        # Only update if the name has changed to avoid API rate limits
        if channel.name != new_name:
            await channel.edit(name=new_name)
            logger.info(f"Updated member count channel to '{new_name}'")
        else:
            logger.info(f"Channel name already up to date: {new_name}")
            
    except Exception as e:
        logger.error(f"Error updating member count channel: {e}", exc_info=True) 