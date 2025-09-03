# You can create a new file, e.g., core/session_utils.py

from db import db

async def get_session_context(session_id: str) -> dict:
    """Fetches the context document for a given session."""
    conversation = await db["conversations"].find_one(
        {"conversationId": session_id},
        {"context": 1} # Only get the context field
    )
    return conversation.get("context", {}) if conversation else {}

async def update_session_context(session_id: str, updates: dict):
    """Updates the context document for a given session."""
    await db["conversations"].update_one(
        {"conversationId": session_id},
        {"$set": {f"context.{key}": value for key, value in updates.items()}},
        upsert=True # Ensure the conversation document is created if it doesn't exist
    )