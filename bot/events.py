import asyncio
import logging
import disnake
from .config import bot
from .utils import update_member_count_channel, increment_member_count, decrement_member_count
from .tasks import member_count_updater
from .database import get_server_config

logger = logging.getLogger(__name__)

def setup_events():
    """
    Register all event listeners with the bot.
    """
    # All event registrations should be done here
    pass

@bot.event
async def on_ready():
    """
    Called when the bot is ready and connected to Discord.
    """
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Initialize member counts for all guilds with a full refresh
    logger.info("Initializing member counts for all guilds")
    for guild in bot.guilds:
        await update_member_count_channel(guild, force_refresh=True)
    
    # Start background task to update member count periodically
    bot.loop.create_task(member_count_updater())

@bot.event
async def on_member_join(member: disnake.Member):
    """
    Assigns roles to a new member and sends a welcome message.
    Handles bots differently by assigning them the Bot role.
    
    Args:
        member: The member who joined the server
    """
    try:
        guild = member.guild
        
        # Get server configuration from database
        server_config = await get_server_config(guild.id)
        
        # Get role IDs from database or fall back to environment variables
        new_user_role_ids = []
        bot_role_ids = []
        
        if server_config:
            # Use database configuration
            notifications_channel_id = server_config.get("notifications_channel_id")
            new_user_role_ids = server_config.get("new_user_role_ids", [])
            bot_role_ids = server_config.get("bot_role_ids", [])
        else:
            # Fall back to environment variables
            from .config import NOTIFICATIONS_CHANNEL_ID, ROLE_USER, ROLE_NEW_ARRIVAL, ROLE_BOT
            notifications_channel_id = NOTIFICATIONS_CHANNEL_ID
            
            if ROLE_USER:
                new_user_role_ids.append(ROLE_USER)
            if ROLE_NEW_ARRIVAL:
                new_user_role_ids.append(ROLE_NEW_ARRIVAL)
            if ROLE_BOT:
                bot_role_ids.append(ROLE_BOT)
        
        if member.bot:
            # Handle bot joins
            logger.info(f"Bot {member.name} joined the server")
            
            # Assign Bot roles if configured
            if bot_role_ids:
                roles_to_add = []
                for role_id in bot_role_ids:
                    role = guild.get_role(role_id)
                    if role:
                        roles_to_add.append(role)
                        logger.info(f"Will assign {role.name} role to bot {member.name}")
                    else:
                        logger.error(f"Bot role with ID {role_id} not found in guild {guild.name}")
                
                if roles_to_add:
                    await member.add_roles(*roles_to_add)
                    logger.info(f"Assigned roles to bot {member.name} in {guild.name}")
            
            # Send notification message for bot joins
            notifications_channel = bot.get_channel(notifications_channel_id)
            if notifications_channel:
                await notifications_channel.send(f"Bot {member.name} has joined the server.")
            else:
                logger.error(f"Notifications channel with ID {notifications_channel_id} not found in guild {guild.name}")
            
            # Bots don't affect the human member count
        else:
            # Handle human user joins
            roles_to_add = []
            
            # Get roles by IDs
            for role_id in new_user_role_ids:
                role = guild.get_role(role_id)
                if role:
                    roles_to_add.append(role)
                    logger.info(f"Will assign {role.name} role to {member.name}")
                else:
                    logger.error(f"User role with ID {role_id} not found in guild {guild.name}")
            
            if roles_to_add:
                await member.add_roles(*roles_to_add)
                logger.info(f"Assigned roles to {member.name} in {guild.name}")
            
            # Send welcome message for human users
            notifications_channel = bot.get_channel(notifications_channel_id)
            if notifications_channel:
                await notifications_channel.send(f"Welcome to the server, {member.mention}!")
            else:
                logger.error(f"Notifications channel with ID {notifications_channel_id} not found in guild {guild.name}")
            
            # Increment the human member count
            increment_member_count(guild.id)
            
            # Update the member count channel
            await update_member_count_channel(guild, force_refresh=False)

    except Exception as e:
        logger.error(f"Error in on_member_join: {e}", exc_info=True)  # Log with traceback

@bot.event
async def on_member_remove(member: disnake.Member):
    """
    Sends a goodbye message when a member leaves.
    
    Args:
        member: The member who left the server
    """
    try:
        guild = member.guild
        logger.info(f"Member removed: {member.name} (ID: {member.id}) from {guild.name}")
        
        # Get server configuration from database
        server_config = await get_server_config(guild.id)
        
        # Get notifications channel ID from database or fall back to environment variable
        if server_config:
            notifications_channel_id = server_config.get("notifications_channel_id")
        else:
            from .config import NOTIFICATIONS_CHANNEL_ID
            notifications_channel_id = NOTIFICATIONS_CHANNEL_ID
        
        # Send goodbye message
        notifications_channel = bot.get_channel(notifications_channel_id)
        if notifications_channel:
            await notifications_channel.send(f"{member.name} has left the server.")
        else:
            logger.error(f"Notifications channel with ID {notifications_channel_id} not found in guild {guild.name}")
        
        # If the member is not a bot, decrement the human member count
        if not member.bot:
            decrement_member_count(guild.id)
        
        # Update the member count channel
        await update_member_count_channel(guild, force_refresh=False)

    except Exception as e:
        logger.error(f"Error in on_member_remove: {e}", exc_info=True) 