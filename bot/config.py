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

# These values are now stored in the database on a per-guild basis
# Setting them to None or 0 as defaults
NOTIFICATIONS_CHANNEL_ID = None
WELCOME_CHANNEL_ID = None  # For backward compatibility
GOODBYE_CHANNEL_ID = None  # For backward compatibility
MEMBER_COUNT_CHANNEL_ID = None

# Role IDs are now stored in the database on a per-guild basis
ROLE_USER = None
ROLE_NEW_ARRIVAL = None
ROLE_BOT = None

# For backward compatibility
ROLE_IDS = []

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