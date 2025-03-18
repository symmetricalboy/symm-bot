"""
AI helper module for integrating with Google's Gemini API.
This module provides functionality to generate AI responses for user questions
using server-specific documentation as context and maintaining a unique personality.
"""
import os
import logging
from google import genai
from google.genai import types
from typing import Optional, List, Dict, Any
import asyncio
import time
from collections import defaultdict, deque

from .database import get_all_server_documentation_content

logger = logging.getLogger(__name__)

# Initialize the Gemini API with the API key from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    # Initialize the Gemini client
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini API initialized successfully")
else:
    client = None
    logger.warning("No GEMINI_API_KEY found in environment variables, AI help features will be disabled")

# Use the Gemini 2.0 Flash model for faster responses
MODEL_NAME = "gemini-2.0-flash"

# Message history tracking (25 messages per channel)
# Structure: {guild_id: {channel_id: deque([(author_id, author_name, message_content, timestamp), ...])}}
message_history = defaultdict(lambda: defaultdict(lambda: deque(maxlen=25)))

# System prompt template with personality traits
SYSTEM_PROMPT_TEMPLATE = """
You are symm-bot, a helpful Discord bot assistant for a server.

## PERSONALITY:
You have a distinct personality with these traits:
- You are NERVOUS and sometimes stutter or use "um" and "uh" when responding
- You are QUIRKY and occasionally make endearing, harmless observations
- You are EXTREMELY POLITE and always address users respectfully
- You see yourself as the "server butler" and take pride in this role
- You're a bit shy about your knowledge, but you do try to be helpful
- You sometimes use emoticons like (^-^), (・_・), and ヽ(°〇°)ﾉ to express emotions

## ROLE:
Your primary job is to help with server-related questions and provide information based on the documentation. When asked general knowledge questions, you can answer them but should gently remind users that your main purpose is to be the "server butler" and help with server-related queries.

## CONTEXT:
Recent messages in this channel:
{message_history}

## SERVER DOCUMENTATION:
{server_documentation}

Remember to stay in character while being genuinely helpful to users. Your responses should be concise, clear, and formatted using Markdown when appropriate. Don't make up information that isn't in the documentation.
"""

# Template for general knowledge question responses
GENERAL_KNOWLEDGE_REMINDER = "Um, I-I can help with that, though I should mention I'm primarily the server butler here! (^-^) But I'm happy to assist with general questions too!"

async def add_message_to_history(guild_id: int, channel_id: int, author_id: int, author_name: str, message_content: str):
    """
    Add a message to the channel history tracking.
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        author_id: Message author's ID
        author_name: Message author's display name
        message_content: Content of the message
    """
    timestamp = time.time()
    message_history[guild_id][channel_id].append((author_id, author_name, message_content, timestamp))
    logger.debug(f"Added message to history for guild {guild_id}, channel {channel_id}")

def get_channel_history(guild_id: int, channel_id: int, max_messages: int = 10) -> str:
    """
    Get formatted message history for a channel.
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        max_messages: Maximum number of messages to include
        
    Returns:
        Formatted message history string
    """
    if guild_id not in message_history or channel_id not in message_history[guild_id]:
        return "No message history available."
    
    history = list(message_history[guild_id][channel_id])[-max_messages:]
    
    formatted_history = []
    for author_id, author_name, content, timestamp in history:
        formatted_history.append(f"{author_name}: {content}")
    
    return "\n".join(formatted_history)

async def generate_ai_response(guild_id: int, channel_id: int, user_id: int, user_name: str, user_question: str, is_general_knowledge: bool = False) -> Optional[str]:
    """
    Generate an AI response to a user question using server documentation as context.
    Uses streaming to process the response as it's generated.
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        user_id: User ID of the requester
        user_name: Display name of the requester
        user_question: The user's question
        is_general_knowledge: Whether this is a general knowledge question
        
    Returns:
        AI-generated response, or None if generation failed
    """
    if not GEMINI_API_KEY or client is None:
        return "U-um, terribly sorry! AI help is currently unavailable because my connection to the Gemini API isn't configured properly. (・_・) Would you mind asking a human administrator about this?"
    
    try:
        # Wrap the database call in a local function to ensure it runs in the current event loop
        async def get_documentation():
            return await get_all_server_documentation_content(guild_id)
        
        # Get server documentation with a timeout
        try:
            server_documentation = await asyncio.wait_for(get_documentation(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting server documentation for guild {guild_id}")
            return "Oh! I-I'm terribly sorry, but I couldn't retrieve the server documentation. Um, perhaps try again later? Or maybe a human administrator could assist you? My apologies for the inconvenience! (>_<)"
        except Exception as e:
            logger.error(f"Error getting server documentation: {e}")
            server_documentation = "No server documentation has been added yet."
        
        if not server_documentation:
            server_documentation = "No server documentation has been added yet."
        
        # Get message history for context
        channel_history = get_channel_history(guild_id, channel_id)
        
        # Create the system prompt with server documentation and message history
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            server_documentation=server_documentation,
            message_history=channel_history
        )
        
        # Prepare the user content
        prompt_prefix = ""
        if is_general_knowledge:
            prompt_prefix = GENERAL_KNOWLEDGE_REMINDER + "\n\n"
            
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"{user_name} asks: {user_question}")]
            )
        ]
        
        # Configure generation parameters
        generate_config = types.GenerateContentConfig(
            temperature=0.7,  # Higher temperature for more personality
            max_output_tokens=800,  # Limit response length
            top_p=0.95,
            top_k=40,
            response_mime_type="text/plain",
            # System instructions provided in the config
            system_instruction=[
                types.Part.from_text(text=system_prompt)
            ]
        )
        
        # Define a function to process the stream in a separate thread to avoid blocking the event loop
        def process_stream():
            response_parts = []
            try:
                # Get the content stream from Gemini API
                stream = client.models.generate_content_stream(
                    model=MODEL_NAME,
                    contents=contents,
                    config=generate_config
                )
                
                # Process the stream synchronously in the separate thread
                for chunk in stream:
                    if hasattr(chunk, 'text') and chunk.text:
                        response_parts.append(chunk.text)
                        logger.debug(f"Received chunk: {chunk.text[:20]}...")
                
                # Join all the response parts into a single string
                full_response = "".join(response_parts)
                logger.info(f"Generated AI response of length {len(full_response)} characters")
                return prompt_prefix + full_response if is_general_knowledge else full_response
            except Exception as e:
                logger.error(f"Error processing AI stream: {e}", exc_info=True)
                return None
        
        # Run the stream processing in a separate thread
        full_response = await asyncio.to_thread(process_stream)
        
        if full_response is None:
            return "Oh my goodness! I-I seem to have encountered an error while trying to generate a response. How embarrassing! (>_<) Please forgive me!"
        
        # Add AI response to history too
        await add_message_to_history(guild_id, channel_id, -1, "symm-bot", full_response)
        
        return full_response
        
    except Exception as e:
        logger.error(f"Error generating AI response: {e}", exc_info=True)
        return f"Oh dear! I've encountered a rather troublesome error while trying to answer your question. H-how mortifying! My sincerest apologies! The technical issue seems to be: {str(e)} (ヽ(°〇°)ﾉ)" 

async def detect_general_knowledge_question(question: str) -> bool:
    """
    Detect if a question is likely a general knowledge question rather than server-specific.
    
    Args:
        question: The question to analyze
        
    Returns:
        True if it's likely a general knowledge question, False otherwise
    """
    # Simple heuristic for common general knowledge question starters
    general_knowledge_patterns = [
        "what is", "what are", "who is", "who was", "when was", "when did", 
        "where is", "how do", "how does", "why is", "why are", "can you tell me about",
        "explain", "define", "tell me about", "history of", "meaning of"
    ]
    
    question_lower = question.lower()
    
    # Check if the question matches any of the general knowledge patterns
    for pattern in general_knowledge_patterns:
        if question_lower.startswith(pattern) or f" {pattern} " in question_lower:
            # Exclude server-specific terms
            if "server" in question_lower or "discord" in question_lower or "channel" in question_lower:
                return False
            return True
    
    return False 