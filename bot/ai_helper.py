"""
AI helper module for integrating with Google's Gemini API.
This module provides functionality to generate AI responses for user questions
using server-specific documentation as context.
"""
import os
import logging
import google.generativeai as genai
from typing import Optional, Dict, Any, List

from .database import get_all_server_documentation_content

logger = logging.getLogger(__name__)

# Initialize the Gemini API with the API key from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Gemini API initialized successfully")
else:
    logger.warning("No GEMINI_API_KEY found in environment variables, AI help features will be disabled")

# Use the Gemini Pro model
MODEL_NAME = "gemini-pro"

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
    
    Args:
        guild_id: Discord guild ID
        user_question: The user's question
        
    Returns:
        AI-generated response, or None if generation failed
    """
    if not GEMINI_API_KEY:
        return "Sorry, AI help is currently unavailable because the Gemini API key is not configured."
    
    try:
        # Get server documentation to use as context
        server_documentation = await get_all_server_documentation_content(guild_id)
        
        if not server_documentation:
            server_documentation = "No server documentation has been added yet."
        
        # Create the system prompt with server documentation
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(server_documentation=server_documentation)
        
        # Set up the model
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Generate response
        response = model.generate_content(
            [
                {"role": "system", "parts": [system_prompt]},
                {"role": "user", "parts": [user_question]}
            ],
            generation_config={
                "temperature": 0.2,  # Lower temperature for more factual responses
                "max_output_tokens": 800,  # Limit response length
                "top_p": 0.95,
                "top_k": 40,
            }
        )
        
        # Return the generated text
        return response.text
        
    except Exception as e:
        logger.error(f"Error generating AI response: {e}", exc_info=True)
        return f"Sorry, I encountered an error while trying to answer your question: {str(e)}" 