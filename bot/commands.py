import logging
import disnake
from disnake.ext import commands
from .config import bot
from .utils import update_member_count_channel

logger = logging.getLogger(__name__)

def setup_commands():
    """
    Register all slash commands with the bot.
    """
    # All command registrations should be done here
    pass

@bot.slash_command(
    name="update_member_count",
    description="Manually updates the member count channel"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def update_member_count(inter: disnake.ApplicationCommandInteraction):
    """Manually updates the member count channel."""
    await inter.response.defer(ephemeral=True)  # Defer the response to avoid timeout
    
    try:
        guild = inter.guild
        await update_member_count_channel(guild)
        await inter.followup.send("Member count channel has been updated!", ephemeral=True)
    except Exception as e:
        logger.error(f"Error in update_member_count command: {e}", exc_info=True)
        await inter.followup.send(f"Error updating member count: {str(e)}", ephemeral=True) 