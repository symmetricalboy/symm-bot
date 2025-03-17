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

# Bot configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
# Combine welcome and goodbye channel IDs into a single notifications channel
NOTIFICATIONS_CHANNEL_ID = int(os.getenv("NOTIFICATIONS_CHANNEL_ID", 
                                      os.getenv("WELCOME_CHANNEL_ID", 
                                              os.getenv("GOODBYE_CHANNEL_ID", 0))))
# For backward compatibility
WELCOME_CHANNEL_ID = NOTIFICATIONS_CHANNEL_ID
GOODBYE_CHANNEL_ID = NOTIFICATIONS_CHANNEL_ID
MEMBER_COUNT_CHANNEL_ID = int(os.getenv("MEMBER_COUNT_CHANNEL_ID"))

# Role IDs
ROLE_USER = int(os.getenv("ROLE_USER", os.getenv("ROLE_ID_1", 0)))  # Fallback to ROLE_ID_1 for compatibility
ROLE_NEW_ARRIVAL = int(os.getenv("ROLE_NEW_ARRIVAL", os.getenv("ROLE_ID_2", 0)))  # Fallback to ROLE_ID_2 for compatibility
ROLE_BOT = int(os.getenv("ROLE_BOT", 0))  # New role for bots

# For backward compatibility
ROLE_IDS = [ROLE_USER, ROLE_NEW_ARRIVAL]

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    logger.warning("DATABASE_URL not set in environment variables")

# Set up intents
intents = disnake.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # Make sure you have the members intent enabled

# Create bot instance
bot = commands.Bot(command_prefix="/", intents=intents) 