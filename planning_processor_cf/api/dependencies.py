# api/dependencies.py
from fastapi import Request, HTTPException
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent import SupplyChainAgent

def get_agent(request: Request) -> "SupplyChainAgent":
    if not hasattr(request.app.state, "agent") or request.app.state.agent is None:
        raise HTTPException(
            status_code=503,
            detail="Agent is not initialized or is currently unavailable."
        )
    return request.app.state.agent