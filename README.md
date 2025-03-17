# symm-bot

A Discord bot for the symm.city server with advanced role management, server configuration features, and AI-powered help system.

## Features

1. **Role Selection Menus** - Create interactive role menus with buttons
2. **Member Count Display** - Shows the current server member count in a voice channel name
3. **Join/Leave Notifications** - Sends notifications when users join or leave
4. **Role Block System** - Prevent users with certain roles from selecting other roles
5. **AI-powered Help** - Ask questions about the server and get AI responses

## Project Structure

The project is organized into modular components to make development easier:

- `bot/` - Main package for the Discord bot
  - `__init__.py` - Package initialization
  - `main.py` - Bot startup and main event loop
  - `config.py` - Configuration loading and setup
  - `commands.py` - Discord slash commands
  - `database.py` - Database models and operations
  - `events.py` - Event handlers for Discord events
  - `utils.py` - Utility functions
  - `ai_helper.py` - AI integration using Google's Gemini API
  - `tasks.py` - Scheduled tasks
- `run.py` - Main entry point for starting the bot

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

## Commands

Here are the main commands provided by the bot:

- `/create_role_menu` - Create a role selection menu with buttons
- `/set_member_count_channel` - Set the channel to display member count
- `/set_notifications_channel` - Set the channel for join/leave notifications
- `/set_new_user_roles` - Set roles to assign to new users who join
- `/set_bot_roles` - Set roles to assign to bots that join
- `/view_server_config` - View the current server configuration
- `/block_role` - Block users with a certain role from selecting another role
- `/unblock_role` - Remove a role blocking relationship
- `/view_role_blocks` - View all role blocking relationships
- `/server_docs add` - Add/update documentation for AI help
- `/server_docs remove` - Remove documentation
- `/server_docs list` - List all documentation
- `/server_docs view` - View a specific documentation entry
- `/help` - Ask a question and get AI-powered help
- `/update_member_count` - Manually update the member count channel

## Configuration

The bot can be configured through either environment variables or directly via Discord commands.

### Setting up Configuration

1. Use the bot commands to set up the server configuration directly.
2. All settings are stored in the database and can be viewed with `/view_server_config`
3. Use the role management commands to set up role menus and role blocks

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