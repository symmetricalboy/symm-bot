import asyncio
import logging
import disnake
from .config import bot, NOTIFICATIONS_CHANNEL_ID, ROLE_USER, ROLE_NEW_ARRIVAL, ROLE_BOT
from .utils import update_member_count_channel, increment_member_count, decrement_member_count
from .tasks import member_count_updater

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
        
        if member.bot:
            # Handle bot joins
            logger.info(f"Bot {member.name} joined the server")
            
            # Assign Bot role if configured
            if ROLE_BOT:
                bot_role = guild.get_role(ROLE_BOT)
                if bot_role:
                    await member.add_roles(bot_role)
                    logger.info(f"Assigned Bot role to {member.name} in {guild.name}")
                else:
                    logger.error(f"Bot role with ID {ROLE_BOT} not found")
            
            # Bots don't affect the human member count
        else:
            # Handle human user joins
            user_role = guild.get_role(ROLE_USER)
            new_arrival_role = guild.get_role(ROLE_NEW_ARRIVAL)
            
            roles_to_add = []
            if user_role:
                roles_to_add.append(user_role)
            else:
                logger.error(f"User role with ID {ROLE_USER} not found")
                
            if new_arrival_role:
                roles_to_add.append(new_arrival_role)
            else:
                logger.error(f"New Arrival role with ID {ROLE_NEW_ARRIVAL} not found")
            
            if roles_to_add:
                await member.add_roles(*roles_to_add)
                logger.info(f"Assigned roles to {member.name} in {guild.name}")
            
            # Send welcome message for human users
            notifications_channel = bot.get_channel(NOTIFICATIONS_CHANNEL_ID)
            if notifications_channel:
                await notifications_channel.send(f"Welcome to the server, {member.mention}!")
            else:
                logger.error(f"Notifications channel with ID {NOTIFICATIONS_CHANNEL_ID} not found")
            
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
        
        # Send goodbye message
        notifications_channel = bot.get_channel(NOTIFICATIONS_CHANNEL_ID)
        if notifications_channel:
            await notifications_channel.send(f"{member.name} has left the server.")
        else:
            logger.error(f"Notifications channel with ID {NOTIFICATIONS_CHANNEL_ID} not found")
        
        # If the member is not a bot, decrement the human member count
        if not member.bot:
            decrement_member_count(guild.id)
        
        # Update the member count channel
        await update_member_count_channel(guild, force_refresh=False)

    except Exception as e:
        logger.error(f"Error in on_member_remove: {e}", exc_info=True) 