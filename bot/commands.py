import logging
import disnake
from disnake.ext import commands
from .config import bot, OWNER_ID
from .utils import update_member_count_channel
from .database import (
    create_role_menu, get_role_menu_by_message, get_role_menu_by_role_id,
    set_member_count_channel, set_notifications_channel, set_new_user_roles, set_bot_roles,
    get_server_config,
    add_role_block, remove_role_block, get_blocked_roles, get_blocking_role, get_role_blocks,
    add_server_documentation, delete_server_documentation, get_server_documentation,
    safe_db_operation
)
from .ai_helper import generate_ai_response

logger = logging.getLogger(__name__)

def setup_commands():
    """
    Register all slash commands with the bot.
    """
    # All command registrations should be done here
    logger.info("Registering commands...")
    
    # We need to register a listener for button interactions with custom_ids that match our format
    # This is a simpler approach than trying to recreate the views on startup
    bot.add_listener(handle_button_interactions, "on_button_click")
    
    logger.info("Commands registered successfully")

async def handle_button_interactions(inter: disnake.MessageInteraction):
    """
    Handle button interactions from persistent views.
    This function is called for any button click after a bot restart.
    Only handles orphaned buttons (those without active views).
    """
    # If this button is already handled by a view, skip it
    if inter.message.id in bot._connection._view_store:
        # This interaction already has a view, let the normal callback handle it
        return
        
    custom_id = inter.component.custom_id
    
    # Check if this is a role button
    if custom_id.startswith("role:"):
        try:
            role_id = int(custom_id.split(":", 1)[1])
            guild = inter.guild
            role = guild.get_role(role_id)
            
            if not role:
                await inter.response.send_message("Error: Role not found.", ephemeral=True)
                return
                
            member = inter.user
            
            # Get the user's current roles
            user_role_ids = [r.id for r in member.roles]
            
            # Check if this role is blocked by any of the user's roles
            # Use safe_db_operation to avoid event loop errors
            blocking_role_id = await safe_db_operation(get_blocking_role, guild.id, user_role_ids, role_id)
            
            if blocking_role_id is not None:
                # Find the role name for better error message
                blocking_role = guild.get_role(blocking_role_id)
                blocking_role_name = blocking_role.name if blocking_role else f"Unknown Role (ID: {blocking_role_id})"
                
                await inter.response.send_message(
                    f"You cannot select the {role.name} role because you have the {blocking_role_name} role.", 
                    ephemeral=True
                )
                return
            
            # Look up the menu configuration from the database
            menu_data = await safe_db_operation(get_role_menu_by_role_id, role_id, guild.id)
            exclusive = menu_data["exclusive"] if menu_data else False
            button_ids = menu_data.get("button_ids", []) if menu_data else []
            
            if exclusive and role not in member.roles:
                # Remove other roles from this menu
                to_remove = [r for r in member.roles if r.id in button_ids]
                if to_remove:
                    await member.remove_roles(*to_remove, reason="Exclusive role selection")
            
            # Toggle the role
            if role in member.roles:
                await member.remove_roles(role, reason="Role menu selection")
                await inter.response.send_message(f"Removed the {role.name} role.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Role menu selection")
                await inter.response.send_message(f"Added the {role.name} role.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in persistent button handler: {e}", exc_info=True)
            await inter.response.send_message("An error occurred while processing your role selection.", ephemeral=True)

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


class RoleButton(disnake.ui.Button):
    def __init__(self, role_id: int, exclusive: bool, guild: disnake.Guild):
        """
        Initialize a role selection button.
        
        Args:
            role_id: The ID of the role this button assigns
            exclusive: Whether this button is part of a mutually exclusive role group
            guild: The guild this button belongs to, used to get role info
        """
        self.role_id = role_id
        self.exclusive = exclusive
        
        # Get the role to use its name and color
        role = guild.get_role(role_id)
        
        # Set default values in case role is not found
        label = f"Unknown Role ({role_id})"
        style = disnake.ButtonStyle.secondary
        
        if role:
            label = role.name
            # Try to match the role color, defaulting to blurple if the role has no color
            if role.color.value:
                # Use red, green, or blurple depending on the main hue of the role color
                r, g, b = role.color.r, role.color.g, role.color.b
                if r > g and r > b:
                    style = disnake.ButtonStyle.danger  # Red for reddish colors
                elif g > r and g > b:
                    style = disnake.ButtonStyle.success  # Green for greenish colors
                else:
                    style = disnake.ButtonStyle.primary  # Blurple for blueish colors
            else:
                style = disnake.ButtonStyle.primary
        
        super().__init__(
            style=style,
            label=label,
            custom_id=f"role:{role_id}"
        )
    
    async def callback(self, interaction: disnake.MessageInteraction):
        """Handle button click to assign or remove a role."""
        member = interaction.user
        guild = interaction.guild
        role = guild.get_role(self.role_id)
        
        if not role:
            try:
                await interaction.response.send_message(f"Error: Role not found.", ephemeral=True)
            except (disnake.errors.InteractionResponded, disnake.errors.HTTPException):
                # If the interaction was already responded to, use followup instead
                await interaction.followup.send(f"Error: Role not found.", ephemeral=True)
            return
        
        try:
            # Get the user's current roles
            user_role_ids = [r.id for r in member.roles]
            
            # Check if this role is blocked by any of the user's roles
            blocking_role_id = await safe_db_operation(get_blocking_role, guild.id, user_role_ids, self.role_id)
            
            if blocking_role_id is not None:
                # Find the role name for better error message
                blocking_role = guild.get_role(blocking_role_id)
                blocking_role_name = blocking_role.name if blocking_role else f"Unknown Role (ID: {blocking_role_id})"
                
                try:
                    await interaction.response.send_message(
                        f"You cannot select the {role.name} role because you have the {blocking_role_name} role.", 
                        ephemeral=True
                    )
                except (disnake.errors.InteractionResponded, disnake.errors.HTTPException):
                    await interaction.followup.send(
                        f"You cannot select the {role.name} role because you have the {blocking_role_name} role.", 
                        ephemeral=True
                    )
                return
            
            # If exclusive, remove all other roles from the same group
            if self.exclusive and role not in member.roles:
                # Get all role IDs from this view
                view_role_ids = [btn.role_id for btn in self.view.children if isinstance(btn, RoleButton)]
                
                # Get all the roles the member has that are in this view
                to_remove = [r for r in member.roles if r.id in view_role_ids]
                
                # Remove all other roles from this group
                if to_remove:
                    await member.remove_roles(*to_remove, reason="Exclusive role selection")
            
            # Toggle the role
            if role in member.roles:
                await member.remove_roles(role, reason="Role menu selection")
                try:
                    await interaction.response.send_message(f"Removed the {role.name} role.", ephemeral=True)
                except (disnake.errors.InteractionResponded, disnake.errors.HTTPException):
                    await interaction.followup.send(f"Removed the {role.name} role.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Role menu selection")
                try:
                    await interaction.response.send_message(f"Added the {role.name} role.", ephemeral=True)
                except (disnake.errors.InteractionResponded, disnake.errors.HTTPException):
                    await interaction.followup.send(f"Added the {role.name} role.", ephemeral=True)
                
        except disnake.Forbidden:
            try:
                await interaction.response.send_message("I don't have permission to manage these roles.", ephemeral=True)
            except (disnake.errors.InteractionResponded, disnake.errors.HTTPException):
                await interaction.followup.send("I don't have permission to manage these roles.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in role button callback: {e}", exc_info=True)
            try:
                await interaction.response.send_message(f"Error managing roles: {str(e)}", ephemeral=True)
            except (disnake.errors.InteractionResponded, disnake.errors.HTTPException):
                await interaction.followup.send(f"Error managing roles: {str(e)}", ephemeral=True)


class RoleSelectionView(disnake.ui.View):
    def __init__(self, role_ids: list, exclusive: bool, guild: disnake.Guild):
        """
        Create a view with role selection buttons.
        
        Args:
            role_ids: List of role IDs to create buttons for
            exclusive: Whether roles are mutually exclusive
            guild: The guild this view belongs to
        """
        super().__init__(timeout=None)  # Persistent view
        
        # Add buttons for each role
        for role_id in role_ids:
            self.add_item(RoleButton(role_id, exclusive, guild))


@bot.slash_command(
    name="create_role_menu",
    description="Create an embed message with role selection buttons"
)
async def cmd_create_role_menu(
    inter: disnake.ApplicationCommandInteraction,
    message: str = commands.Param(description="Message to display in the embed"),
    exclusive: bool = commands.Param(description="Whether roles are mutually exclusive (true) or multiple can be selected (false)"),
    roles: str = commands.Param(description="List of role mentions or IDs separated by spaces, use | to create a new line of buttons"),
    title: str = commands.Param(description="Title for the embed", default="Role Selection")
):
    """Create an embed with buttons for users to self-assign roles."""
    # Check if the user is the bot owner
    if inter.author.id != OWNER_ID:
        await inter.response.send_message("This command is restricted to the bot owner.", ephemeral=True)
        return
    
    await inter.response.defer(ephemeral=True)
    
    try:
        # Parse the roles parameter
        role_groups = []
        for group in roles.split("|"):
            role_ids = []
            for role_str in group.strip().split():
                try:
                    # Check if it's a role mention (<@&ROLE_ID>)
                    if role_str.startswith("<@&") and role_str.endswith(">"):
                        # Extract the role ID from the mention
                        role_id_str = role_str[3:-1]  # Remove <@& and >
                        try:
                            role_id = int(role_id_str)
                        except ValueError:
                            await inter.followup.send(f"Warning: '{role_str}' contains an invalid role ID.", ephemeral=True)
                            continue
                    else:
                        # Try to parse as a direct role ID
                        try:
                            role_id = int(role_str)
                        except ValueError:
                            await inter.followup.send(f"Warning: '{role_str}' is not a valid role ID or mention.", ephemeral=True)
                            continue
                    
                    # Verify the role exists
                    role = inter.guild.get_role(role_id)
                    if role:
                        role_ids.append(role_id)
                    else:
                        await inter.followup.send(f"Warning: Role with ID {role_id} not found.", ephemeral=True)
                except Exception as e:
                    logger.error(f"Error parsing role '{role_str}': {e}")
                    await inter.followup.send(f"Warning: Error parsing '{role_str}'. Please use valid role mentions or IDs.", ephemeral=True)
            if role_ids:
                role_groups.append(role_ids)
        
        if not role_groups:
            await inter.followup.send("No valid roles were provided.", ephemeral=True)
            return
        
        # Create an embed for the message
        embed = disnake.Embed(
            title=title,
            description=message,
            color=disnake.Color.blue()
        )
        
        # Add additional information about how to use the menu
        if exclusive:
            embed.add_field(
                name="Instructions", 
                value="You can select only one role from this menu. Selecting a new role will remove your previous selection.",
                inline=False
            )
        else:
            embed.add_field(
                name="Instructions", 
                value="You can select multiple roles from this menu. Click a button to add or remove a role.",
                inline=False
            )
        
        embed.set_footer(text=f"Created by {inter.author.display_name}", icon_url=inter.author.display_avatar.url)
        
        # Message IDs for database records
        message_ids = []
        
        # For each group of roles, create a separate view
        for i, role_ids in enumerate(role_groups):
            view = RoleSelectionView(role_ids, exclusive, inter.guild)
            
            # For the first group, send with the embed
            if i == 0:
                role_msg = await inter.channel.send(embed=embed, view=view)
            else:
                # For subsequent groups, send without an embed
                role_msg = await inter.channel.send(view=view)
            
            # Record the message ID
            message_ids.append(role_msg.id)
        
        # Store the role menu configuration in the database
        for i, msg_id in enumerate(message_ids):
            await safe_db_operation(
                create_role_menu,
                message_id=msg_id,
                guild_id=inter.guild.id,
                channel_id=inter.channel.id,
                exclusive=exclusive,
                created_by=inter.author.id,
                role_groups=[role_groups[i]]  # Each message gets its own group
            )
        
        await inter.followup.send("Role selection menu created successfully!", ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in create_role_menu command: {e}", exc_info=True)
        await inter.followup.send(f"Error creating role menu: {str(e)}", ephemeral=True)


# Server Configuration Commands
@bot.slash_command(
    name="set_member_count_channel",
    description="Set the channel where member count is displayed"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_set_member_count_channel(
    inter: disnake.ApplicationCommandInteraction,
    channel: disnake.VoiceChannel = commands.Param(description="The voice channel to use for member count")
):
    """Set the channel where member count is displayed."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        channel_id = channel.id
        
        # Check if the bot has permissions to manage the channel
        member = inter.guild.get_member(bot.user.id)
        permissions = channel.permissions_for(member)
        
        if not permissions.manage_channels:
            await inter.followup.send(
                "I don't have permission to manage that voice channel. "
                "Please give me the 'Manage Channels' permission for that channel.", 
                ephemeral=True
            )
            return
        
        # Save to database
        success = await set_member_count_channel(guild_id, channel_id)
        
        if success:
            # Update the channel immediately
            await update_member_count_channel(inter.guild, force_refresh=True)
            await inter.followup.send(
                f"Member count channel set to {channel.mention}. The channel has been updated.", 
                ephemeral=True
            )
        else:
            await inter.followup.send("Failed to set member count channel.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in set_member_count_channel command: {e}", exc_info=True)
        await inter.followup.send(f"Error setting member count channel: {str(e)}", ephemeral=True)


@bot.slash_command(
    name="set_notifications_channel",
    description="Set the channel for join/leave notifications"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_set_notifications_channel(
    inter: disnake.ApplicationCommandInteraction,
    channel: disnake.TextChannel = commands.Param(description="The text channel to use for notifications")
):
    """Set the channel where join/leave notifications are sent."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        channel_id = channel.id
        
        # Check if the bot has permissions to send messages in the channel
        member = inter.guild.get_member(bot.user.id)
        permissions = channel.permissions_for(member)
        
        if not permissions.send_messages:
            await inter.followup.send(
                "I don't have permission to send messages in that channel. "
                "Please give me the 'Send Messages' permission for that channel.", 
                ephemeral=True
            )
            return
        
        # Save to database
        success = await set_notifications_channel(guild_id, channel_id)
        
        if success:
            await inter.followup.send(
                f"Notifications channel set to {channel.mention}. "
                "Join and leave messages will now be sent there.", 
                ephemeral=True
            )
        else:
            await inter.followup.send("Failed to set notifications channel.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in set_notifications_channel command: {e}", exc_info=True)
        await inter.followup.send(f"Error setting notifications channel: {str(e)}", ephemeral=True)


@bot.slash_command(
    name="set_new_user_roles",
    description="Set the roles to assign to new users who join the server"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_set_new_user_roles(
    inter: disnake.ApplicationCommandInteraction,
    roles: str = commands.Param(description="List of role IDs separated by spaces")
):
    """Set the roles to assign to new users who join the server."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        
        # Parse the roles parameter
        role_ids = []
        valid_roles = []
        invalid_roles = []
        
        for role_id_str in roles.strip().split():
            try:
                role_id = int(role_id_str)
                role = inter.guild.get_role(role_id)
                if role:
                    role_ids.append(role_id)
                    valid_roles.append(role)
                else:
                    invalid_roles.append(role_id_str)
            except ValueError:
                invalid_roles.append(role_id_str)
        
        if not role_ids:
            await inter.followup.send("No valid roles were provided.", ephemeral=True)
            return
        
        # Check if the bot has permissions to manage roles
        member = inter.guild.get_member(bot.user.id)
        permissions = inter.guild.permissions_for(member)
        
        if not permissions.manage_roles:
            await inter.followup.send(
                "I don't have permission to manage roles. "
                "Please give me the 'Manage Roles' permission.",
                ephemeral=True
            )
            return
        
        # Check if bot can assign all the roles (bot's highest role must be higher than roles it assigns)
        bot_top_role = member.top_role
        for role in valid_roles:
            if role >= bot_top_role:
                await inter.followup.send(
                    f"I cannot assign the role {role.name} because it's higher than or equal to my highest role. "
                    "Please move my role higher in the role hierarchy.",
                    ephemeral=True
                )
                return
        
        # Save to database
        success = await set_new_user_roles(guild_id, role_ids)
        
        if success:
            role_mentions = ", ".join(role.mention for role in valid_roles)
            message = f"New user roles set to: {role_mentions}"
            
            if invalid_roles:
                message += f"\n\nThe following role IDs were invalid: {', '.join(invalid_roles)}"
            
            await inter.followup.send(message, ephemeral=True)
        else:
            await inter.followup.send("Failed to set new user roles.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in set_new_user_roles command: {e}", exc_info=True)
        await inter.followup.send(f"Error setting new user roles: {str(e)}", ephemeral=True)


@bot.slash_command(
    name="set_bot_roles",
    description="Set the roles to assign to bots that join the server"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_set_bot_roles(
    inter: disnake.ApplicationCommandInteraction,
    roles: str = commands.Param(description="List of role IDs separated by spaces")
):
    """Set the roles to assign to bots that join the server."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        
        # Parse the roles parameter
        role_ids = []
        valid_roles = []
        invalid_roles = []
        
        for role_id_str in roles.strip().split():
            try:
                role_id = int(role_id_str)
                role = inter.guild.get_role(role_id)
                if role:
                    role_ids.append(role_id)
                    valid_roles.append(role)
                else:
                    invalid_roles.append(role_id_str)
            except ValueError:
                invalid_roles.append(role_id_str)
        
        if not role_ids:
            await inter.followup.send("No valid roles were provided.", ephemeral=True)
            return
        
        # Check if the bot has permissions to manage roles
        member = inter.guild.get_member(bot.user.id)
        permissions = inter.guild.permissions_for(member)
        
        if not permissions.manage_roles:
            await inter.followup.send(
                "I don't have permission to manage roles. "
                "Please give me the 'Manage Roles' permission.",
                ephemeral=True
            )
            return
        
        # Check if bot can assign all the roles (bot's highest role must be higher than roles it assigns)
        bot_top_role = member.top_role
        for role in valid_roles:
            if role >= bot_top_role:
                await inter.followup.send(
                    f"I cannot assign the role {role.name} because it's higher than or equal to my highest role. "
                    "Please move my role higher in the role hierarchy.",
                    ephemeral=True
                )
                return
        
        # Save to database
        success = await set_bot_roles(guild_id, role_ids)
        
        if success:
            role_mentions = ", ".join(role.mention for role in valid_roles)
            message = f"Bot roles set to: {role_mentions}"
            
            if invalid_roles:
                message += f"\n\nThe following role IDs were invalid: {', '.join(invalid_roles)}"
            
            await inter.followup.send(message, ephemeral=True)
        else:
            await inter.followup.send("Failed to set bot roles.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in set_bot_roles command: {e}", exc_info=True)
        await inter.followup.send(f"Error setting bot roles: {str(e)}", ephemeral=True)


@bot.slash_command(
    name="view_server_config",
    description="View current server configuration"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_view_server_config(inter: disnake.ApplicationCommandInteraction):
    """View the current server configuration."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        
        # Get configuration from database
        config = await get_server_config(guild_id)
        
        if not config:
            await inter.followup.send("No configuration found for this server.", ephemeral=True)
            return
        
        # Create an embed with the configuration
        embed = disnake.Embed(
            title="Server Configuration",
            description=f"Configuration for {inter.guild.name}",
            color=disnake.Color.blue()
        )
        
        # Member Count Channel
        member_count_channel_id = config.get("member_count_channel_id")
        if member_count_channel_id:
            channel = inter.guild.get_channel(member_count_channel_id)
            if channel:
                embed.add_field(
                    name="Member Count Channel",
                    value=f"{channel.mention} (ID: {member_count_channel_id})",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Member Count Channel",
                    value=f"Channel not found (ID: {member_count_channel_id})",
                    inline=False
                )
        else:
            embed.add_field(
                name="Member Count Channel",
                value="Not set",
                inline=False
            )
        
        # Notifications Channel
        notifications_channel_id = config.get("notifications_channel_id")
        if notifications_channel_id:
            channel = inter.guild.get_channel(notifications_channel_id)
            if channel:
                embed.add_field(
                    name="Notifications Channel",
                    value=f"{channel.mention} (ID: {notifications_channel_id})",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Notifications Channel",
                    value=f"Channel not found (ID: {notifications_channel_id})",
                    inline=False
                )
        else:
            embed.add_field(
                name="Notifications Channel",
                value="Not set",
                inline=False
            )
        
        # New User Roles
        new_user_role_ids = config.get("new_user_role_ids", [])
        if new_user_role_ids:
            role_mentions = []
            for role_id in new_user_role_ids:
                role = inter.guild.get_role(role_id)
                if role:
                    role_mentions.append(f"{role.mention} (ID: {role_id})")
                else:
                    role_mentions.append(f"Role not found (ID: {role_id})")
            
            embed.add_field(
                name="New User Roles",
                value="\n".join(role_mentions),
                inline=False
            )
        else:
            embed.add_field(
                name="New User Roles",
                value="Not set",
                inline=False
            )
        
        # Bot Roles
        bot_role_ids = config.get("bot_role_ids", [])
        if bot_role_ids:
            role_mentions = []
            for role_id in bot_role_ids:
                role = inter.guild.get_role(role_id)
                if role:
                    role_mentions.append(f"{role.mention} (ID: {role_id})")
                else:
                    role_mentions.append(f"Role not found (ID: {role_id})")
            
            embed.add_field(
                name="Bot Roles",
                value="\n".join(role_mentions),
                inline=False
            )
        else:
            embed.add_field(
                name="Bot Roles",
                value="Not set",
                inline=False
            )
        
        await inter.followup.send(embed=embed, ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in view_server_config command: {e}", exc_info=True)
        await inter.followup.send("An error occurred while retrieving server configuration.", ephemeral=True)


@bot.slash_command(
    name="block_role",
    description="Set a role that blocks users from selecting another role"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_block_role(
    inter: disnake.ApplicationCommandInteraction,
    blocking_role: disnake.Role = commands.Param(description="The role that blocks"),
    blocked_role: disnake.Role = commands.Param(description="The role that is blocked")
):
    """
    Set a role that blocks users from selecting another role.
    Users with the blocking role will not be able to select the blocked role.
    """
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        blocking_role_id = blocking_role.id
        blocked_role_id = blocked_role.id
        
        # Don't allow blocking the same role
        if blocking_role_id == blocked_role_id:
            await inter.followup.send("A role cannot block itself.", ephemeral=True)
            return
        
        # Save to database
        success = await add_role_block(guild_id, blocking_role_id, blocked_role_id)
        
        if success:
            await inter.followup.send(
                f"Role block added. Users with the {blocking_role.mention} role will not be able to select the {blocked_role.mention} role.", 
                ephemeral=True
            )
        else:
            await inter.followup.send("Failed to add role block.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in block_role command: {e}", exc_info=True)
        await inter.followup.send(f"Error adding role block: {str(e)}", ephemeral=True)


@bot.slash_command(
    name="unblock_role",
    description="Remove a role blocking relationship"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_unblock_role(
    inter: disnake.ApplicationCommandInteraction,
    blocking_role: disnake.Role = commands.Param(description="The role that blocks"),
    blocked_role: disnake.Role = commands.Param(description="The role that is blocked")
):
    """
    Remove a role blocking relationship.
    This allows users with the previously blocking role to select the previously blocked role.
    """
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        blocking_role_id = blocking_role.id
        blocked_role_id = blocked_role.id
        
        # Save to database
        success = await remove_role_block(guild_id, blocking_role_id, blocked_role_id)
        
        if success:
            await inter.followup.send(
                f"Role block removed. Users with the {blocking_role.mention} role can now select the {blocked_role.mention} role.", 
                ephemeral=True
            )
        else:
            await inter.followup.send("Failed to remove role block.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in unblock_role command: {e}", exc_info=True)
        await inter.followup.send(f"Error removing role block: {str(e)}", ephemeral=True)


@bot.slash_command(
    name="view_role_blocks",
    description="View all role blocking relationships"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def cmd_view_role_blocks(inter: disnake.ApplicationCommandInteraction):
    """View all role blocking relationships in the server."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        
        # Get all role blocks
        blocks = await get_role_blocks(guild_id)
        
        if not blocks:
            await inter.followup.send("No role blocks found.", ephemeral=True)
            return
        
        # Create an embed with the blocks
        embed = disnake.Embed(
            title="Role Blocks",
            description="Roles that block users from selecting other roles",
            color=disnake.Color.blue()
        )
        
        for i, block in enumerate(blocks, start=1):
            blocking_role = inter.guild.get_role(block["blocking_role_id"])
            blocked_role = inter.guild.get_role(block["blocked_role_id"])
            
            blocking_role_name = blocking_role.name if blocking_role else f"Unknown Role (ID: {block['blocking_role_id']})"
            blocked_role_name = blocked_role.name if blocked_role else f"Unknown Role (ID: {block['blocked_role_id']})"
            
            embed.add_field(
                name=f"Block {i}",
                value=f"Users with {blocking_role_name} cannot select {blocked_role_name}",
                inline=False
            )
        
        await inter.followup.send(embed=embed, ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in view_role_blocks command: {e}", exc_info=True)
        await inter.followup.send(f"Error viewing role blocks: {str(e)}", ephemeral=True)


# Server Documentation Commands
@bot.slash_command(
    name="server_docs",
    description="Manage server documentation for the AI help system"
)
@commands.has_permissions(administrator=True)  # Only administrators can use this command
async def server_docs(inter: disnake.ApplicationCommandInteraction):
    """Command group for managing server documentation."""
    pass


@server_docs.sub_command(
    name="add",
    description="Add or update server documentation for the AI help system"
)
async def add_docs(
    inter: disnake.ApplicationCommandInteraction,
    title: str = commands.Param(description="Title for this documentation section"),
    content: str = commands.Param(description="The documentation content")
):
    """
    Add or update server documentation for the AI help system.
    This information will be used to answer user questions with the /help command.
    """
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        created_by = inter.author.id
        
        # Add to database
        doc_id = await add_server_documentation(
            guild_id=guild_id,
            title=title,
            content=content,
            created_by=created_by
        )
        
        if doc_id:
            await inter.followup.send(
                f"Server documentation '{title}' has been added/updated successfully. "
                f"Users can now ask questions about this information using the `/help` command.",
                ephemeral=True
            )
        else:
            await inter.followup.send("Failed to add server documentation.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in add_docs command: {e}", exc_info=True)
        await inter.followup.send(f"Error adding server documentation: {str(e)}", ephemeral=True)


@server_docs.sub_command(
    name="remove",
    description="Remove server documentation"
)
async def remove_docs(
    inter: disnake.ApplicationCommandInteraction,
    title: str = commands.Param(description="Title of the documentation to remove")
):
    """Remove server documentation from the AI help system."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        
        # Delete from database
        success = await delete_server_documentation(guild_id, title)
        
        if success:
            await inter.followup.send(
                f"Server documentation '{title}' has been removed successfully.",
                ephemeral=True
            )
        else:
            await inter.followup.send(f"Failed to remove server documentation '{title}'.", ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in remove_docs command: {e}", exc_info=True)
        await inter.followup.send(f"Error removing server documentation: {str(e)}", ephemeral=True)


@server_docs.sub_command(
    name="list",
    description="List all server documentation"
)
async def list_docs(inter: disnake.ApplicationCommandInteraction):
    """List all server documentation in the AI help system."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        
        # Get all documentation
        docs = await get_server_documentation(guild_id)
        
        if not docs:
            await inter.followup.send("No server documentation found.", ephemeral=True)
            return
        
        # Create an embed to display the documentation
        embed = disnake.Embed(
            title="Server Documentation",
            description="Documentation used by the AI help system",
            color=disnake.Color.blue()
        )
        
        for doc in docs:
            # Truncate content if too long
            content = doc["content"]
            if len(content) > 100:
                content = content[:97] + "..."
            
            embed.add_field(
                name=doc["title"],
                value=content,
                inline=False
            )
        
        await inter.followup.send(embed=embed, ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in list_docs command: {e}", exc_info=True)
        await inter.followup.send(f"Error listing server documentation: {str(e)}", ephemeral=True)


@server_docs.sub_command(
    name="view",
    description="View a specific server documentation entry"
)
async def view_docs(
    inter: disnake.ApplicationCommandInteraction,
    title: str = commands.Param(description="Title of the documentation to view")
):
    """View a specific server documentation entry in the AI help system."""
    await inter.response.defer(ephemeral=True)
    
    try:
        guild_id = inter.guild.id
        
        # Get documentation
        docs = await get_server_documentation(guild_id, title)
        
        if not docs:
            await inter.followup.send(f"No server documentation found with title '{title}'.", ephemeral=True)
            return
        
        doc = docs[0]
        
        # Create an embed to display the documentation
        embed = disnake.Embed(
            title=doc["title"],
            description=doc["content"],
            color=disnake.Color.blue()
        )
        
        # Add metadata
        if doc["created_by"]:
            try:
                created_by = await bot.fetch_user(doc["created_by"])
                embed.set_footer(text=f"Created by: {created_by.display_name}")
            except:
                embed.set_footer(text=f"Created by: Unknown (ID: {doc['created_by']})")
        
        if doc["updated_at"]:
            embed.timestamp = doc["updated_at"]
        
        await inter.followup.send(embed=embed, ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error in view_docs command: {e}", exc_info=True)
        await inter.followup.send(f"Error viewing server documentation: {str(e)}", ephemeral=True)


# Help command that uses AI to answer user questions
@bot.slash_command(
    name="help",
    description="Ask a question about the server and get an AI-powered answer"
)
async def help_command(
    inter: disnake.ApplicationCommandInteraction,
    question: str = commands.Param(description="Your question about the server")
):
    """
    Ask a question about the server and get an AI-powered answer.
    The AI will use server documentation added by administrators to answer your question.
    """
    await inter.response.defer()  # This might take a moment, so defer the response
    
    try:
        guild_id = inter.guild.id
        
        # Generate AI response
        response = await generate_ai_response(guild_id, question)
        
        if not response:
            await inter.followup.send(
                "I'm sorry, I couldn't generate a response to your question. "
                "Please try asking something else or contact a server administrator."
            )
            return
        
        # Create an embed for the response
        embed = disnake.Embed(
            title=f"Q: {question}",
            description=response,
            color=disnake.Color.blurple()
        )
        
        embed.set_footer(text="Powered by Gemini AI | Based on server documentation")
        
        await inter.followup.send(embed=embed)
    
    except Exception as e:
        logger.error(f"Error in help command: {e}", exc_info=True)
        await inter.followup.send(
            f"Sorry, I encountered an error while trying to answer your question: {str(e)}"
        ) 