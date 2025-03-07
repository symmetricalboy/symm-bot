import asyncio
import asyncpg
import logging
import os

import disnake
from disnake.ext import commands
from dotenv import load_dotenv


# --- Initialization ---

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID"))
GOODBYE_CHANNEL_ID = int(os.getenv("GOODBYE_CHANNEL_ID"))
MEMBER_COUNT_CHANNEL_ID = int(os.getenv("MEMBER_COUNT_CHANNEL_ID"))

ROLE_IDS = [
    int(os.getenv("ROLE_ID_1")),
    int(os.getenv("ROLE_ID_2"))
]

intents = disnake.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # Make sure you have the members intent enabled

bot = commands.Bot(command_prefix="/", intents=intents)


# --- Helper Functions ---

async def get_roles_by_ids(guild: disnake.Guild, role_ids: list[int]) -> list[disnake.Role]:
    roles = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            roles.append(role)
        else:
            logger.error(f"Role with ID {role_id} not found in guild {guild.name}")
    return roles

async def update_member_count_channel(guild: disnake.Guild):
    """
    Updates the member count channel name to show the total number of members in the server.
    """
    try:
        channel = guild.get_channel(MEMBER_COUNT_CHANNEL_ID)
        if not channel:
            logger.error(f"Member count channel with ID {MEMBER_COUNT_CHANNEL_ID} not found")
            return
            
        # Format: "Members: 123"
        new_name = f"Members: {guild.member_count}"
        
        # Only update if the name has changed to avoid API rate limits
        if channel.name != new_name:
            await channel.edit(name=new_name)
            logger.info(f"Updated member count channel to '{new_name}'")
            
    except Exception as e:
        logger.error(f"Error updating member count channel: {e}", exc_info=True)


# --- Event Listeners ---

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Update member count for all guilds when bot starts
    for guild in bot.guilds:
        await update_member_count_channel(guild)
    
    # Start background task to update member count periodically
    bot.loop.create_task(member_count_updater())

async def member_count_updater():
    """
    Background task that updates the member count channel every hour.
    """
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild in bot.guilds:
            await update_member_count_channel(guild)
        # Update once per hour to avoid hitting rate limits
        await asyncio.sleep(3600)

@bot.event
async def on_member_join(member: disnake.Member):
    """
    Assigns roles to a new member and sends a welcome message.
    """
    try:
        guild = member.guild
        roles = await get_roles_by_ids(guild, ROLE_IDS)

        if roles:
            await member.add_roles(*roles)
            logger.info(f"Assigned roles to {member.name} in {guild.name}")

        # Send welcome message
        welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel:
            await welcome_channel.send(f"Welcome to the server, {member.mention}!")
        else:
            logger.error(f"Welcome channel with ID {WELCOME_CHANNEL_ID} not found")
            
        # Update member count when a new member joins
        await update_member_count_channel(guild)

    except Exception as e:
        logger.error(f"Error in on_member_join: {e}", exc_info=True)  # Log with traceback

@bot.event
async def on_member_remove(member: disnake.Member):
    """
    Sends a goodbye message when a member leaves.
    """
    try:
        guild = member.guild
        goodbye_channel = bot.get_channel(GOODBYE_CHANNEL_ID)
        if goodbye_channel:
            await goodbye_channel.send(f"{member.name} has left the server.")
        else:
            logger.error(f"Goodbye channel with ID {GOODBYE_CHANNEL_ID} not found")
            
        # Update member count when a member leaves
        await update_member_count_channel(guild)

    except Exception as e:
        logger.error(f"Error in on_member_remove: {e}", exc_info=True)

bot.run(DISCORD_BOT_TOKEN)
