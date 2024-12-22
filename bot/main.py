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

ROLE_IDS = [
    int(os.getenv("ROLE_ID_1")),
    int(os.getenv("ROLE_ID_2"))
]


intents = disnake.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)


# --- Helper Functions ---

async def get_roles_by_ids(guild: disnake.Guild, role_ids: list[int]) -> list[disnake.Role]:
    roles = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            roles.append(role)
    return roles


# --- Event Listeners ---

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

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

    except Exception as e:
        logger.error(f"Error in on_member_join: {e}")


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

    except Exception as e:
        logger.error(f"Error in on_member_remove: {e}")


bot.run(DISCORD_BOT_TOKEN)