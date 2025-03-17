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
    # Use separate background task to avoid event loop issues
    logger.info("Initializing member counts for all guilds")
    
    # Schedule the initialization in a background task
    bot.loop.create_task(initialize_member_counts())
    
    # Start background task to update member count periodically
    if not hasattr(bot, 'member_count_task') or bot.member_count_task.done():
        bot.member_count_task = bot.loop.create_task(member_count_updater())
        logger.info("Started member count updater task")

async def initialize_member_counts():
    """Initializes member counts for all guilds in a background task."""
    try:
        # Add a small delay to avoid initialization conflicts during startup
        await asyncio.sleep(2)
        
        for guild in bot.guilds:
            try:
                # Use a small timeout to prevent blocking during initialization
                update_task = asyncio.create_task(update_member_count_channel(guild, force_refresh=True))
                try:
                    # Set a reasonable timeout for each guild's update
                    await asyncio.wait_for(update_task, timeout=15.0)
                except asyncio.TimeoutError:
                    logger.error(f"Timeout while initializing member count for guild {guild.name}")
                
                # Add a small delay between guilds to avoid rate limits
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error initializing member count for guild {guild.name}: {e}")
    except Exception as e:
        logger.error(f"Error in member count initialization: {e}", exc_info=True)

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
        
        # Get server configuration from database - wrap in try/except
        server_config = None
        try:
            server_config = await get_server_config(guild.id)
        except Exception as e:
            logger.error(f"Error getting server config in on_member_join: {e}")
            # Continue with defaults
        
        # Get role IDs from database
        new_user_role_ids = []
        bot_role_ids = []
        notifications_channel_id = None
        
        if server_config:
            # Use database configuration
            notifications_channel_id = server_config.get("notifications_channel_id")
            new_user_role_ids = server_config.get("new_user_role_ids", [])
            bot_role_ids = server_config.get("bot_role_ids", [])
        
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
            if notifications_channel_id:
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
            if notifications_channel_id:
                notifications_channel = bot.get_channel(notifications_channel_id)
                if notifications_channel:
                    await notifications_channel.send(f"Welcome to the server, {member.mention}!")
                else:
                    logger.error(f"Notifications channel with ID {notifications_channel_id} not found in guild {guild.name}")
            
            # Increment the human member count
            increment_member_count(guild.id)
            
            # Update the member count channel in a background task to avoid blocking
            bot.loop.create_task(update_member_count_channel(guild, force_refresh=False))

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
        
        # Get server configuration from database - wrap in try/except
        server_config = None
        notifications_channel_id = None
        
        try:
            server_config = await get_server_config(guild.id)
            if server_config:
                notifications_channel_id = server_config.get("notifications_channel_id")
        except Exception as e:
            logger.error(f"Error getting server config in on_member_remove: {e}")
            # Continue with default
        
        # Send goodbye message
        if notifications_channel_id:
            notifications_channel = bot.get_channel(notifications_channel_id)
            if notifications_channel:
                await notifications_channel.send(f"{member.name} has left the server.")
            else:
                logger.error(f"Notifications channel with ID {notifications_channel_id} not found in guild {guild.name}")
        
        # If the member is not a bot, decrement the human member count
        if not member.bot:
            decrement_member_count(guild.id)
        
        # Update the member count channel in a background task to avoid blocking
        bot.loop.create_task(update_member_count_channel(guild, force_refresh=False))

    except Exception as e:
        logger.error(f"Error in on_member_remove: {e}", exc_info=True) 