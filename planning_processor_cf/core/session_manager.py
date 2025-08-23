# core/session_manager.py
from typing import Dict, Optional
from datetime import datetime, timedelta
import threading
import uuid
from models.session_models import SessionData
from utils.exceptions import SessionNotFoundError
from config.settings import settings

class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.RLock()
        self.session_timeout = timedelta(seconds=settings.session_timeout)

    def create_session(self, session_id: Optional[str] = None) -> str:
        with self._lock:
            if not session_id:
                session_id = str(uuid.uuid4())
            
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionData(
                    session_id=session_id,
                    created_at=datetime.now(),
                    last_accessed=datetime.now()
                )
            return session_id

    def get_session(self, session_id: str) -> SessionData:
        with self._lock:
            if not self.session_exists(session_id):
                raise SessionNotFoundError(f"Session {session_id} not found or has expired")
            session = self._sessions[session_id]
            session.last_accessed = datetime.now()
            return session

    def update_session(self, session_id: str, **kwargs) -> None:
        with self._lock:
            session = self.get_session(session_id)
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            session.last_accessed = datetime.now()

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            if session_id not in self._sessions:
                return False
            session = self._sessions[session_id]
            if datetime.now() - session.last_accessed > self.session_timeout:
                del self._sessions[session_id]
                return False
            return True

    def cleanup_expired_sessions(self) -> int:
        with self._lock:
            now = datetime.now()
            expired_ids = [
                sid for sid, sdata in self._sessions.items()
                if now - sdata.last_accessed > self.session_timeout
            ]
            for sid in expired_ids:
                del self._sessions[sid]
            return len(expired_ids)
    
    def get_active_session_count(self) -> int:
        with self._lock:
            return len(self._sessions)