# tools/base_tool.py
from abc import ABC
import json
import logging
from core.session_manager import SessionManager

logger = logging.getLogger(__name__)

class BaseTool(ABC):
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def log_tool_execution(self, tool_name: str, session_id: str, **params):
        logger.info(f"Executing {tool_name} for session {session_id} with params: {params}")

    def format_success_response(self, result: any) -> str:
        return json.dumps({"result": result})

    def format_error_response(self, error_message: str) -> str:
        return json.dumps({"error": error_message})

    def format_empty_response(self, message: str) -> str:
        return json.dumps({"result": message})