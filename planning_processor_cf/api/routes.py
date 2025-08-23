# api/routes.py
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from models.api_models import ChatRequest, ChatResponse, HealthResponse
from core.agent import SupplyChainAgent
from .dependencies import get_agent

# Create a router object. This is like a mini-FastAPI app that can be
# included in the main app.
router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, agent: SupplyChainAgent = Depends(get_agent)):
    try:
       
        session_id = request.session_id or str(uuid.uuid4())

        if not agent.session_manager.session_exists(session_id):
            agent.initialize_session(session_id)

        response_text = agent.process_message(session_id, request.message)
        
        return ChatResponse(response=response_text, session_id=session_id)

    except Exception as e:
        logger.error(
            f"Error processing chat message for session {request.session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An internal server error occurred while processing your message.")


@router.get("/health", response_model=HealthResponse)
async def health_check(agent: SupplyChainAgent = Depends(get_agent)):
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        sessions_active=agent.session_manager.get_active_session_count()
    )


@router.post("/sessions/{session_id}/cleanup")
async def cleanup_session(session_id: str, agent: SupplyChainAgent = Depends(get_agent)):
    try:
        agent.cleanup_session(session_id)
        return {"message": f"Session {session_id} cleaned up successfully"}
    except Exception as e:
        logger.warning(f"Failed to cleanup session {session_id}: {e}")
        raise HTTPException(
            status_code=404, detail=f"Session not found or already expired: {str(e)}")


@router.post("/cleanup-expired-sessions")
async def cleanup_expired_sessions(agent: SupplyChainAgent = Depends(get_agent)):
    try:
        cleaned_count = agent.session_manager.cleanup_expired_sessions()
        return {"message": f"Cleaned up {cleaned_count} expired sessions"}
    except Exception as e:
        logger.error(
            f"Manual cleanup of expired sessions failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Cleanup failed: {str(e)}")
