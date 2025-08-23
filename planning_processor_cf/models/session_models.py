# models/session_models.py
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

class ActionPlan(BaseModel):
    actions: List[Dict[str, Any]]
    created_at: datetime = Field(default_factory=datetime.now)

class SessionData(BaseModel):
    session_id: str
    created_at: datetime
    last_accessed: datetime
    last_queried_ids: Optional[List[str]] = None
    last_action_plan: Optional[ActionPlan] = None
    context: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True