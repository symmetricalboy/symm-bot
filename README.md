# symm-bot

A Discord bot for the symm.city server with advanced role management, server configuration features, and AI-powered help system.

## Features

- **Member Count Display**: Automatically updates a voice channel to show current member count
- **Welcome & Goodbye Messages**: Sends notifications when members join or leave
- **Role Management System**:
  - Interactive role selection menus with persistent buttons
  - Role exclusivity options (mutually exclusive roles within a menu)
  - Role blocking system (prevent users with certain roles from selecting other roles)
- **Server Configuration**: Store server settings in a database for improved flexibility
- **Multi-Server Support**: Configure different settings for each server
- **AI-Powered Help System**:
  - Answer user questions about the server using Google's Gemini AI
  - Custom server documentation managed by administrators
  - Natural language responses to help queries

## Project Structure

The project is organized into modular components to make development easier:

- `bot/config.py` - Configuration variables and bot initialization
- `bot/commands.py` - Slash commands and command registration
- `bot/events.py` - Event listeners (on_ready, on_member_join, etc.)
- `bot/utils.py` - Utility functions used across the bot
- `bot/tasks.py` - Background tasks that run periodically
- `bot/database.py` - Database models and operations
- `bot/ai_helper.py` - AI integration with Gemini for help responses
- `bot/main.py` - Module initialization and coordination
- `run.py` - Entry point to start the bot

## Development

To add new functionality:

1. **Commands**: Add new slash commands to `bot/commands.py`
2. **Event Listeners**: Add new event listeners to `bot/events.py`
3. **Background Tasks**: Add new background tasks to `bot/tasks.py`
4. **Database Models**: Add new models to `bot/database.py`
5. **Utility Functions**: Add new utility functions to `bot/utils.py`

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# Bot Configuration
DISCORD_BOT_TOKEN=your_bot_token_here
OWNER_ID=your_discord_id_here

# Database Configuration
DATABASE_URL=postgresql://username:password@hostname:port/database_name

# Optional Configuration
GEMINI_API_KEY=your_gemini_api_key_here  # Required for AI help features
```

## Database Setup

The bot uses PostgreSQL to store server configurations, role menus, and role relationships.

1. Create a PostgreSQL database
2. Set the `DATABASE_URL` environment variable
3. The bot will automatically create the necessary tables on first run
4. If upgrading from a previous version, use the `/migrate_config` command to transfer environment variable settings to the database

## Available Commands

### Role Management

- `/create_role_menu` - Create a new role selection menu with buttons
- `/block_role` - Set a role that prevents users from selecting another role
- `/unblock_role` - Remove a role blocking relationship
- `/view_role_blocks` - View all role blocking relationships in the server

### Server Configuration

- `/set_member_count_channel` - Set the channel to display member count
- `/set_notifications_channel` - Set the channel for join/leave notifications
- `/set_new_user_roles` - Set roles to assign to new human users
- `/set_bot_roles` - Set roles to assign to new bot users
- `/view_server_config` - View current server configuration
- `/migrate_config` - Migrate environment variables to database storage

### AI Help System

- `/help` - Ask a question about the server and get an AI-powered response
- `/server_docs add` - Add or update server documentation (admin only)
- `/server_docs remove` - Remove server documentation (admin only)
- `/server_docs list` - List all server documentation (admin only)
- `/server_docs view` - View a specific documentation entry (admin only)

## Running the Bot

1. Install dependencies: `pip install -r requirements.txt`
2. Set up your `.env` file with the required environment variables
3. Run the bot: `python run.py`

## Role Blocking System

The role blocking system allows you to define roles that prevent users from selecting other roles:

1. If a user has a blocking role, they cannot select any roles that are blocked by that role
2. When attempting to select a blocked role, the user will receive a message explaining which of their roles is blocking the selection
3. This system works across all role menus, unlike the exclusive roles feature which only works within a single menu
4. Administrators can manage role blocks using the `/block_role`, `/unblock_role`, and `/view_role_blocks` commands

## AI Help System

The AI help system allows users to ask natural language questions about the server and get AI-generated responses:

1. Administrators can add documentation about the server using `/server_docs add`
2. Users can ask questions using the `/help` command
3. The bot uses Google's Gemini AI to generate responses based on the server documentation
4. The system is designed to only provide information that exists in the server documentation
5. Responses are formatted with Markdown for better readability
6. To use this feature, you must set the `GEMINI_API_KEY` in your environment variables