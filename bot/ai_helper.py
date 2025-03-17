"""
AI helper module for integrating with Google's Gemini API.
This module provides functionality to generate AI responses for user questions
using server-specific documentation as context.
"""
import os
import logging
from google import genai
from google.genai import types
from typing import Optional, Dict, Any, List
import asyncio

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

# System prompt template
SYSTEM_PROMPT_TEMPLATE = """
You are a helpful Discord bot assistant for a server.

Your job is to answer questions about the server, its rules, features, and how to use it.
Base your answers on the server documentation provided below. If you don't know something
or if the information isn't in the documentation, politely say so and suggest talking to a 
human moderator or admin.

Be concise, helpful, and friendly in your responses. Format your answers clearly using
Markdown when appropriate. Don't make up information that isn't in the documentation.

SERVER DOCUMENTATION:
{server_documentation}

Remember, your goal is to be genuinely helpful to users by providing accurate information
based solely on the provided documentation.
"""

async def generate_ai_response(guild_id: int, user_question: str) -> Optional[str]:
    """
    Generate an AI response to a user question using server documentation as context.
    Uses streaming to process the response as it's generated.
    
    Args:
        guild_id: Discord guild ID
        user_question: The user's question
        
    Returns:
        AI-generated response, or None if generation failed
    """
    if not GEMINI_API_KEY or client is None:
        return "Sorry, AI help is currently unavailable because the Gemini API key is not configured."
    
    try:
        # Wrap the database call in a local function to ensure it runs in the current event loop
        async def get_documentation():
            return await get_all_server_documentation_content(guild_id)
        
        # Get server documentation with a timeout
        try:
            server_documentation = await asyncio.wait_for(get_documentation(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting server documentation for guild {guild_id}")
            return "Sorry, I couldn't retrieve the server documentation. Please try again later or contact a server administrator."
        except Exception as e:
            logger.error(f"Error getting server documentation: {e}")
            server_documentation = "No server documentation has been added yet."
        
        if not server_documentation:
            server_documentation = "No server documentation has been added yet."
        
        # Create the system prompt with server documentation
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(server_documentation=server_documentation)
        
        # Prepare the user content
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_question)]
            )
        ]
        
        # Configure generation parameters
        generate_config = types.GenerateContentConfig(
            temperature=0.2,  # Lower temperature for more factual responses
            max_output_tokens=800,  # Limit response length
            top_p=0.95,
            top_k=40,
            response_mime_type="text/plain",
            # System instructions provided in the config
            system_instruction=[
                types.Part.from_text(text=system_prompt)
            ]
        )
        
        # Generate the response using streaming
        response_parts = []
        
        # Get the content stream from Gemini API
        stream = client.models.generate_content_stream(
            model=MODEL_NAME,
            contents=contents,
            config=generate_config
        )
        
        # The Gemini API returns a regular generator, not an async generator
        # So we use a regular for loop instead of async for
        for chunk in stream:
            if hasattr(chunk, 'text') and chunk.text:
                response_parts.append(chunk.text)
                logger.debug(f"Received chunk: {chunk.text[:20]}...")
        
        # Join all the response parts into a single string
        full_response = "".join(response_parts)
        logger.info(f"Generated AI response of length {len(full_response)} characters")
        
        return full_response
        
    except Exception as e:
        logger.error(f"Error generating AI response: {e}", exc_info=True)
        return f"Sorry, I encountered an error while trying to answer your question: {str(e)}" 