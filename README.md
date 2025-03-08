# symm-bot

A Discord bot for the symm.city server.

## Project Structure

The project is organized into modular components to make development easier:

- `bot/config.py` - Configuration variables and bot initialization
- `bot/commands.py` - Slash commands and command registration
- `bot/events.py` - Event listeners (on_ready, on_member_join, etc.)
- `bot/utils.py` - Utility functions used across the bot
- `bot/tasks.py` - Background tasks that run periodically
- `bot/main.py` - Module initialization and coordination
- `run.py` - Entry point to start the bot

## Development

To add new functionality:

1. **Commands**: Add new slash commands to `bot/commands.py`
2. **Event Listeners**: Add new event listeners to `bot/events.py`
3. **Background Tasks**: Add new background tasks to `bot/tasks.py`
4. **Utility Functions**: Add new utility functions to `bot/utils.py`

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# Bot Configuration
DISCORD_BOT_TOKEN=your_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here  # Optional: For AI features
OWNER_ID=your_discord_id_here

# Channel IDs
NOTIFICATIONS_CHANNEL_ID=channel_id_for_welcome_and_goodbye_messages
MEMBER_COUNT_CHANNEL_ID=channel_id_for_member_count

# Role IDs
ROLE_USER=id_for_user_role
ROLE_NEW_ARRIVAL=id_for_new_arrival_role
ROLE_BOT=id_for_bot_role
```

## Running the Bot

1. Install dependencies: `pip install -r requirements.txt`
2. Set up your `.env` file with the required environment variables
3. Run the bot: `python run.py`