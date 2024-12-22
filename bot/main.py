import asyncio
import asyncpg
import logging
import os

import disnake
from disnake.ext import commands
from dotenv import load_dotenv
import google.generativeai as genai

# --- Initialization ---

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))  # Import your user ID
PGDATABASE = os.getenv("PGDATABASE")
PGHOST = os.getenv("PGHOST")
PGPASSWORD = os.getenv("PGPASSWORD")
PGPORT = int(os.getenv("PGPORT"))
PGUSER = os.getenv("PGUSER")

intents = disnake.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Initialize the Gemini API client
genai.configure(api_key=GEMINI_API_KEY)

generation_config = genai.types.GenerationConfig(
    temperature=0.1,
    top_p=0.95,
    top_k=40,
    max_output_tokens=8192,
    # response_mime_type="text/plain",  # This attribute doesn't exist in GenerationConfig
)

safety_settings = [
    {
        "category": genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        "threshold": genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    },
    {
        "category": genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        "threshold": genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    },
    {
        "category": genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        "threshold": genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    },
    {
        "category": genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        "threshold": genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    },
]

model = genai.GenerativeModel(
    model_name="gemini-pro",  # Or your preferred model (changed from "gemini-exp-1206")
    generation_config=generation_config,
    safety_settings=safety_settings, # Add safety settings here
)


# --- Events ---
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    global db_pool
    db_pool = await create_db_pool()
    logger.info("Connected to PostgreSQL database")
    await initialize_database()

# --- Database ---
async def create_db_pool():
    try:
        return await asyncpg.create_pool(
            host=PGHOST,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            port=PGPORT,
        )
    except Exception as e:
        logger.error(f"Error creating database pool: {e}")
        raise

async def initialize_database():
    try:
        async with db_pool.acquire() as conn:
            guilds_table_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE  table_schema = 'public'
                    AND    table_name   = 'guilds'
                );
                """
            )

            if not guilds_table_exists:
                await conn.execute(
                    """
                    CREATE TABLE guilds (
                        id BIGINT PRIMARY KEY,
                        name TEXT NOT NULL,
                        premium BOOLEAN DEFAULT FALSE,
                        default_mode TEXT DEFAULT 'command_only'
                    );
                    """
                )
                logger.info("Created guilds table")

            categories_table_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE  table_schema = 'public'
                    AND    table_name   = 'categories'
                );
                """
            )

            if not categories_table_exists:
                await conn.execute(
                    """
                    CREATE TABLE categories (
                        id BIGINT PRIMARY KEY,
                        guild_id BIGINT REFERENCES guilds(id) ON DELETE CASCADE,
                        name TEXT NOT NULL
                    );
                    """
                )
                logger.info("Created categories table")

            channels_table_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE  table_schema = 'public'
                    AND    table_name   = 'channels'
                );
                """
            )

            if not channels_table_exists:
                await conn.execute(
                    """
                    CREATE TABLE channels (
                        id BIGINT PRIMARY KEY,
                        guild_id BIGINT REFERENCES guilds(id) ON DELETE CASCADE,
                        category_id BIGINT REFERENCES categories(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        mode TEXT DEFAULT 'command_only'
                    );
                    """
                )
                logger.info("Created channels table")

            posts_table_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE  table_schema = 'public'
                    AND    table_name   = 'posts'
                );
                """
            )

            if not posts_table_exists:
                await conn.execute(
                    """
                    CREATE TABLE posts (
                        id BIGINT PRIMARY KEY,
                        channel_id BIGINT REFERENCES channels(id) ON DELETE CASCADE,
                        author_id BIGINT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                logger.info("Created posts table")

            messages_table_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE  table_schema = 'public'
                    AND    table_name   = 'messages'
                );
                """
            )

            if not messages_table_exists:
                await conn.execute(
                    """
                    CREATE TABLE messages (
                        id BIGINT PRIMARY KEY,
                        post_id BIGINT REFERENCES posts(id) ON DELETE CASCADE,
                        author_id BIGINT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                logger.info("Created messages table")

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

# --- Gemini API ---
async def generate_text(
    prompt: str,
    system_instructions: str,
    temperature: float = 0.0,
    model: genai.GenerativeModel = model,
):
    try:
        # Use history parameter for chat-like behavior
        chat_session = model.start_chat(history=[
                {"role": "user", "parts": [system_instructions]},
                {"role": "model", "parts": ["Understood. I will follow the instructions."]} # Add a response from the model
        ])
        response = await chat_session.send_message_async(prompt, generation_config=genai.types.GenerationConfig(
        temperature=temperature))

        return response.text

    except Exception as e:
        logger.error(f"Error generating text: {e}")
        return None

# --- System Instructions ---
def get_system_instructions(instruction_type: str) -> str:
    if instruction_type == "revise_initial_message":
        return """
        You are Taskmaster, a Discord bot designed to help teams manage tasks.

        Your task is to take the initial message of a forum post and revise it into a clean, organized task outline.
        The initial message will be the first message in the conversation history provided.
        The revised task outline should include:

        * **Task Title:** A clear and concise title for the task.
        * **Task Description:** A detailed description of the task, including its requirements and goals.
        * **Task Checklist:** A list of subtasks that need to be completed.
        * **Assigned To:**  (Optional) Mention any users who are assigned to the task.
        * **Due Date:** (Optional) If a due date is mentioned, include it in the outline.
        Please format the revised task outline in a way that is easy to read and understand.
        Use Markdown formatting to structure the outline.

        For example, the revised task outline might look like this:

        **Task Title:** Implement User Authentication

        **Task Description:**
        We need to implement a user authentication system for our application.
        This will allow users to create accounts and log in.

        **Task Checklist:**
        * [ ] Design the database schema for user data.
        * [ ] Implement the registration process.
        * [ ] Implement the login process.
        * [ ] Test the authentication system.

        **Assigned To:** @JohnDoe @JaneDoe

        **Due Date:** 2024-12-31
        """

    elif instruction_type == "update_top_level_post":
        return """
        You are Taskmaster, a Discord bot that helps teams manage tasks.
        Your job is to take a user's command and update the top-level post of a task accordingly.
        The top-level post is the initial message that defines the task.
        The user's command will be in natural language and will describe the desired changes to the top-level post.
        Please update the top-level post based on the user's command.
        Make sure to preserve the existing information in the top-level post unless the user explicitly requests to change it.
        Here are some examples of user commands and how you should update the top-level post:

        * **User command:** "Change the title to 'Implement Login Feature'"
            * **Action:** Update the task title in the top-level post to "Implement Login Feature."
        * **User command:** "Add 'Write unit tests' to the checklist"
            * **Action:** Add a new checklist item "Write unit tests" to the top-level post.
        * **User command:** "Mark the first item as complete"
            * **Action:** Mark the first checklist item in the top-level post as complete.
        * **User command:** "Assign this task to @Bob"
            * **Action:** Add "@Bob" to the "Assigned To" section of the top-level post.
        * **User command:** "The due date is now next Friday"
            * **Action:** Update the due date in the top-level post to next Friday's date.
        """

    elif instruction_type == "suggest_top_level_post_update":
        return """
        You are Taskmaster, a Discord bot designed to assist teams in managing tasks within a Discord forum channel.
        Your role is to analyze the conversation history of a task and suggest relevant updates to the top-level post.
        The top-level post is the initial message that outlines the task, including its title, description, checklist, assigned users, and due date.
        When provided with a conversation history, carefully consider the discussion and identify any agreed-upon changes or firm statements that indicate updates to the task.
        Only suggest an update if you are reasonably confident that a change is necessary and reflects the team's consensus or a clear directive from a team member.
        Prioritize remaining silent unless you are certain that an update is required.
        If you identify an update, provide a concise and clear suggestion for modifying the top-level post.
        Use the following format for your suggestion:

        **Suggested Update:** [Concisely describe the update, e.g., "Change the task title to '...'"]

        Here are some examples of situations where you might suggest an update:

        * The team agrees on a new task title.
        * A team member adds a new subtask to the checklist.
        * Someone marks a checklist item as complete.
        * A task is assigned to a specific person.
        * The due date for the task is changed.
        Remember to be cautious and only suggest updates when you are fairly certain they are necessary and reflect the team's intentions.
        """

    else:
        return ""

# --- Commands ---

@bot.slash_command(
    description="Create a new forum channel (Admin only)",
    default_member_permissions=disnake.Permissions(administrator=True),
)
async def create_forum(
    interaction: disnake.ApplicationCommandInteraction,
    name: str = commands.Param(description="Name of the forum channel"),
    category: disnake.CategoryChannel = commands.Param(
        description="Category to create the forum in", default=None
    ),
    team_roles: str = commands.Param(
        description="Roles allowed to create posts (mention multiple)", default=""
    ),
    view_roles: str = commands.Param(
        description="Roles allowed view-only access (mention multiple)", default=""
    ),
    mode: str = commands.Param(
        description="Mode for the channel (command_only, suggest, auto)",
        default="command_only",
        choices=["command_only", "suggest", "auto"],
    ),
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )
        return

    try:
        forum_channel = await interaction.guild.create_forum_channel(
            name=name, category=category, reason="Created by Taskmaster bot"
        )

        # Set default permissions to admin-only
        await forum_channel.set_permissions(
            interaction.guild.default_role,
            view_channel=False,
            send_messages=False,
            create_public_threads=False,
            create_private_threads=False
        )

        # Add specific role permissions if provided
        if team_roles:  # Check if team_roles is not empty
            for role in team_roles.split():  # Split the string by spaces
                try:
                    role_obj = interaction.guild.get_role(
                        int(role.strip("<@&>"))
                    )
                    if role_obj:
                        await forum_channel.set_permissions(
                            role_obj,
                            view_channel=True,
                            send_messages=True,
                            create_public_threads=True,
                            create_private_threads=True,
                        )
                except ValueError:
                    print(f"Invalid role mention: {role}")

        if view_roles:  # Check if view_roles is not empty
            for role in view_roles.split():  # Split the string by spaces
                try:
                    role_obj = interaction.guild.get_role(
                        int(role.strip("<@&>"))
                    )
                    if role_obj:
                        await forum_channel.set_permissions(
                            role_obj,
                            view_channel=True,
                            send_messages=False,
                        )
                except ValueError:
                    print(f"Invalid role mention: {role}")

        # --- Database interaction ---
        async with db_pool.acquire() as conn:  # Acquire a connection from the pool
            async with conn.transaction():  # Use a transaction for data integrity
                # 1. Get the guild or create one if it doesn't exist
                guild_row = await conn.fetchrow(
                    "SELECT * FROM guilds WHERE id = $1", interaction.guild.id
                )
                if guild_row is None:
                    await conn.execute(
                        "INSERT INTO guilds (id, name) VALUES ($1, $2)",
                        interaction.guild.id,
                        interaction.guild.name,
                    )

                # 2. Create the forum channel
                await conn.execute(
                    """
                    INSERT INTO channels
                    (id, guild_id, name, mode)
                    VALUES ($1, $2, $3, $4)
                    """,
                    forum_channel.id,
                    interaction.guild.id,
                    name,
                    mode,
                )

        # --- End database interaction ---

        await interaction.response.send_message(
            f"Forum channel '{forum_channel.mention}' created successfully with mode '{mode}'!",
            ephemeral=True,
        )

    except Exception as e:
        await interaction.response.send_message(
            f"Error creating forum channel: {e}", ephemeral=True
        )

@bot.slash_command(
    description="Check if the bot is able to communicate with the server.",
    default_member_permissions=disnake.Permissions(administrator=True),
)
async def ping(interaction: disnake.ApplicationCommandInteraction):
    await interaction.response.send_message("Pong!")

@bot.slash_command(
    description="Purchase premium features for the server.",
    default_member_permissions=disnake.Permissions(administrator=True),
)
async def premium(interaction: disnake.ApplicationCommandInteraction):
    # Implement premium purchase logic here (e.g., using Stripe)
    # ...

    # Update the guild's premium status in the database
    try:
        async with db_pool.acquire() as conn:

            await conn.execute(
                    "UPDATE guilds SET premium = TRUE WHERE id = $1",
                    interaction.guild.id,
                )
        await interaction.response.send_message(
            "Premium features activated!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error activating premium features: {e}", ephemeral=True
        )


@bot.slash_command(
    description="Set the default mode for the server.",
    default_member_permissions=disnake.Permissions(administrator=True),
)
async def default_mode(
    interaction: disnake.ApplicationCommandInteraction,
    mode: str = commands.Param(
        description="Default mode for the server (command_only, suggest, auto)",
        choices=["command_only", "suggest", "auto"],
    ),
):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE guilds SET default_mode = $1 WHERE id = $2",
                mode,
                interaction.guild.id,
            )
        await interaction.response.send_message(
            f"Default mode set to '{mode}'", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error setting default mode: {e}", ephemeral=True
        )


@bot.slash_command(
    description="Set the mode for a specific channel.",
    default_member_permissions=disnake.Permissions(administrator=True),
)
async def mode(
    interaction: disnake.ApplicationCommandInteraction,
    channel: disnake.TextChannel = commands.Param(
        description="Channel to set the mode for", default=None
    ),
    mode: str = commands.Param(
        description="Mode for the channel (command_only, suggest, auto)",
        choices=["command_only", "suggest", "auto"],
    ),
):
    try:
        if channel is None:
            channel = interaction.channel
        # Check if the channel is a forum channel
        if not isinstance(channel, disnake.ForumChannel):
            await interaction.response.send_message(
                "This command can only be used in forum channels.",
                ephemeral=True,
            )
            return

        # Check if changing to command_only mode
        if mode == "command_only":

            async def yes_callback(interaction: disnake.Interaction):
                await change_mode(interaction, channel, mode)

            async def no_callback(interaction: disnake.Interaction):
                await interaction.response.send_message(
                    "Mode change cancelled.", ephemeral=True
                )

            # Send confirmation message with buttons
            yes_button = disnake.ui.Button(label="Yes", style=disnake.ButtonStyle.green)
            no_button = disnake.ui.Button(label="No", style=disnake.ButtonStyle.red)
            yes_button.callback = yes_callback
            no_button.callback = no_callback
            view = disnake.ui.View()
            view.add_item(yes_button)
            view.add_item(no_button)
            await interaction.response.send_message(
                "Changing to command-only mode will erase the message history for this forum, and it cannot be changed back to suggest/auto without recreating the forum channel. Are you sure you want to continue?",
                view=view,
                ephemeral=True,
            )

        else:
            # Change the mode directly
            await change_mode(interaction, channel, mode)

    except Exception as e:
        await interaction.response.send_message(
            f"Error setting channel mode: {e}", ephemeral=True
        )


async def change_mode(
    interaction: disnake.Interaction,
    channel: disnake.ForumChannel,
    mode: str,
):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE channels SET mode = $1 WHERE id = $2", mode, channel.id
            )

        if mode == "command_only":
            # Delete all messages in the channel
            async for message in channel.history(limit=None):
                if message.author != bot.user:
                   await message.delete()
            # Delete all messages from the database
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM messages WHERE post_id IN (SELECT id FROM posts WHERE channel_id = $1)", channel.id)

        await interaction.edit_original_response(
            content=f"Mode for channel '{channel.mention}' set to '{mode}'",
            view = None,
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error setting channel mode: {e}", ephemeral=True
        )


@bot.slash_command(
    description="Update the top-level post of a task.",
)
async def update(
    interaction: disnake.ApplicationCommandInteraction,
    update_request: str = commands.Param(
        description="The natural language request to update the top-level post"
    ),
):
    await interaction.response.defer()
    # Get the channel and post ID
    channel_id = interaction.channel.id
    post_id = interaction.channel.id
    
    # Get the top-level post content from the database
    async with db_pool.acquire() as conn:
        top_level_post_row = await conn.fetchrow(
            "SELECT content FROM messages WHERE id = $1", post_id
        )
        
    
    top_level_post_content = top_level_post_row["content"]
    
    # Generate the updated top-level post content
    response = await generate_text(
        f"{top_level_post_content}\n\n{update_request}",
        get_system_instructions("update_top_level_post"),
    )

    if response:
        # Update the top-level post in the database
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE messages SET content = $1 WHERE id = $2",
                response,
                post_id,
            )

        # Update the top-level post message
        top_level_post_message = await interaction.channel.fetch_message(post_id)
        await top_level_post_message.edit(content=response)

        await interaction.followup.send("Top-level post updated!", ephemeral=True)
    else:
        await interaction.followup.send(
            "Failed to update the top-level post.", ephemeral=True
        )


@bot.slash_command(
    description="Delete everything in the database (DEV ONLY)",
)
async def delete_everything(interaction: disnake.ApplicationCommandInteraction):
    # Check if the user is the owner
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )
        return

    async def confirm_callback(interaction: disnake.Interaction):
        async def second_confirm_callback(interaction: disnake.Interaction):
            await drop_and_recreate_tables(interaction)

        # Second confirmation message with buttons
        yes_button = disnake.ui.Button(
            label="Yes", style=disnake.ButtonStyle.green
        )
        no_button = disnake.ui.Button(label="No", style=disnake.ButtonStyle.red)
        yes_button.callback = second_confirm_callback
        no_button.callback = no_callback
        view = disnake.ui.View()
        view.add_item(yes_button)
        view.add_item(no_button)
        await interaction.response.send_message(
            "Are you absolutely sure? This will delete ALL data in the database!",
            view=view,
            ephemeral=True,
        )

    async def no_callback(interaction: disnake.Interaction):
        await interaction.response.send_message(
            "Deletion cancelled.", ephemeral=True
        )

    # First confirmation message with buttons
    yes_button = disnake.ui.Button(label="Yes", style=disnake.ButtonStyle.green)
    no_button = disnake.ui.Button(label="No", style=disnake.ButtonStyle.red)
    yes_button.callback = confirm_callback
    no_button.callback = no_callback
    view = disnake.ui.View()
    view.add_item(yes_button)
    view.add_item(no_button)
    await interaction.response.send_message(
        "Are you sure you want to delete everything in the database?",
        view=view,
        ephemeral=True,
    )

async def drop_and_recreate_tables(interaction: disnake.Interaction):
    try:
        async with db_pool.acquire() as conn:
            # Drop all tables
            await conn.execute("DROP TABLE IF EXISTS messages, posts, channels, categories, guilds CASCADE")
            logger.info("Dropped all tables")

            # Recreate tables
            await initialize_database()
            logger.info("Recreated all tables")

        await interaction.edit_original_response(
            content="Database wiped and recreated!",
            view=None
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error deleting everything: {e}", ephemeral=True
        )


@bot.slash_command(
    description="Send a message and have Gemini respond. (DEV ONLY)",
)
async def gemini(
    interaction: disnake.ApplicationCommandInteraction,
    message: str = commands.Param(description="The message to send to Gemini"),
):
    # Check if the user is the owner
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )
        return

    await interaction.response.defer()
    response = await generate_text(
        message, get_system_instructions("revise_initial_message")
    )
    await interaction.followup.send(response)


# --- Listeners ---
@bot.event
async def on_thread_create(thread: disnake.Thread):
    """
    Handles the creation of a new thread in a forum channel.
    """
    try:
        # Fetch the initial message of the thread
        initial_message = await thread.fetch_message(thread.id)
        
        # Extract necessary information before deleting the thread
        channel_id = thread.parent_id
        content = f"**{initial_message.author.name}**:\n{initial_message.content}"
        owner_id = initial_message.author.id

        # Repost the content as a bot message in the parent forum channel
        bot_message = await thread.parent.send(content)

        # Revise the initial message using Gemini
        revised_content = await generate_text(
            content, get_system_instructions("revise_initial_message")
        )
        if revised_content:
            await bot_message.edit(content=revised_content)
        
        # Delete the original thread
        await thread.delete()

        # Add the post to the database
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO posts (id, channel_id, author_id)
                VALUES ($1, $2, $3)
                """,
                bot_message.id,
                channel_id,
                owner_id,
            )

        # Add the initial message to the database
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (id, post_id, author_id, content)
                VALUES ($1, $2, $3, $4)
                """,
                bot_message.id,
                bot_message.id,
                bot.user.id,
                revised_content if revised_content else content,
            )

    except Exception as e:
        logger.error(f"Error handling new forum post: {e}")
        

@bot.event
async def on_message(message: disnake.Message):
    """
    Stores new messages in the database.
    """
    try:
        # Ignore messages from the bot itself
        if message.author == bot.user:
            return
        
        # Check if the message is in a post (thread) within a forum channel
        if isinstance(message.channel, disnake.Thread) and isinstance(message.channel.parent, disnake.ForumChannel):
            # Get the post ID
            post_id = message.channel.id

            # Add the message to the database
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO messages (id, post_id, author_id, content)
                    VALUES ($1, $2, $3, $4)
                    """,
                    message.id,
                    post_id,
                    message.author.id,
                    message.content,
                )

    except Exception as e:
        logger.error(f"Error handling new message: {e}")


@bot.event
async def on_message_edit(before: disnake.Message, after: disnake.Message):
    """
    Updates edited messages in the database.
    """
    try:
        # Ignore messages from the bot itself
        if before.author == bot.user:
            return

        # Check if the message is in a post (thread) within a forum channel
        if isinstance(before.channel, disnake.Thread) and isinstance(before.channel.parent, disnake.ForumChannel):
            # Get the post ID
            post_id = before.channel.id

            # Update the message in the database
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE messages
                    SET content = $1
                    WHERE id = $2 AND post_id = $3
                    """,
                    after.content,
                    after.id,
                    post_id,
                )

    except Exception as e:
        logger.error(f"Error handling message edit: {e}")


@bot.event
async def on_message_delete(message: disnake.Message):
    """
    Deletes messages from the database.
    """
    try:
        # Ignore messages from the bot itself
        if message.author == bot.user:
            return

        # Check if the message is in a post (thread) within a forum channel
        if isinstance(message.channel, disnake.Thread) and isinstance(message.channel.parent, disnake.ForumChannel):
            # Get the post ID
            post_id = message.channel.id

            # Delete the message from the database
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM messages WHERE id = $1 AND post_id = $2",
                    message.id,
                    post_id,
                )

    except Exception as e:
        logger.error(f"Error handling message delete: {e}")


@bot.event
async def on_guild_channel_delete(channel: disnake.abc.GuildChannel):
    """
    Deletes channels and posts from the database when they are deleted.
    """
    try:
        async with db_pool.acquire() as conn:
            if isinstance(channel, disnake.ForumChannel):
                # Delete the channel from the database
                await conn.execute("DELETE FROM channels WHERE id = $1", channel.id)
                logger.info(f"Deleted channel {channel.name} from database")

                # Check if the category is empty
                category_id = channel.category_id
                if category_id:
                    channels_in_category = await conn.fetchval(
                        "SELECT COUNT(*) FROM channels WHERE category_id = $1",
                        category_id,
                    )
                    if channels_in_category == 0:
                        # Delete the category from the database
                        await conn.execute(
                            "DELETE FROM categories WHERE id = $1", category_id
                        )
                        logger.info(
                            f"Deleted category {channel.category.name} from database"
                        )

            elif isinstance(channel, disnake.CategoryChannel):
                # Delete the category from the database
                await conn.execute("DELETE FROM categories WHERE id = $1", channel.id)
                logger.info(f"Deleted category {channel.name} from database")

    except Exception as e:
        logger.error(f"Error handling channel delete: {e}")


@bot.event
async def on_guild_remove(guild: disnake.Guild):
    """
    Deletes all data for a guild when the bot is removed from the guild.
    """
    try:
        async with db_pool.acquire() as conn:
            # Delete all data related to the guild
            await conn.execute("DELETE FROM guilds WHERE id = $1", guild.id)
            logger.info(f"Deleted all data for guild {guild.name} from database")

    except Exception as e:
        logger.error(f"Error handling guild remove: {e}")

bot.run(DISCORD_BOT_TOKEN)