# core/agent.py
from typing import Optional
from .session_manager import SessionManager
from .ai_chat_manager import AIChatManager
from services.data_service import DataService
from services.odoo_service import OdooService
from services.planning_service import PlanningService
from tools.query_tool import QueryTool
from tools.odoo_query_tool import OdooQueryTool
from tools.verification_tool import VerificationTool
from tools.planning_tool import PlanningTool
from tools.execution_tool import ExecutionTool
from tools.rescheduling_tool import ReschedulingTool
from utils.response_formatter import ResponseFormatter
from utils.exceptions import AgentError
import logging

logger = logging.getLogger(__name__)

class SupplyChainAgent:
    def __init__(self):
        # Initialize managers and services
        self.session_manager = SessionManager()
        self.ai_chat_manager = AIChatManager()
        self.data_service = DataService()
        self.odoo_service = OdooService()
        self.planning_service = PlanningService(self.data_service, self.odoo_service)
        self.response_formatter = ResponseFormatter()
        self._initialize_tools()

    def _initialize_tools(self):
        query_tool = QueryTool(self.data_service, self.session_manager)
        odoo_query_tool = OdooQueryTool(self.odoo_service, self.session_manager)
        verification_tool = VerificationTool(self.odoo_service, self.session_manager)
        planning_tool = PlanningTool(self.planning_service, self.session_manager)
        execution_tool = ExecutionTool(self.planning_service, self.session_manager)
        rescheduling_tool = ReschedulingTool(
            self.data_service, 
            self.planning_service, 
            self.session_manager
        )

        tools = [
            query_tool.query_planned_orders,
            odoo_query_tool.get_odoo_order_details,
            verification_tool.check_order_status_in_odoo,
            planning_tool.create_execution_plan,
            execution_tool.execute_plan,
            rescheduling_tool.analyze_rescheduling_eligibility,
            rescheduling_tool.create_rescheduling_plan,
            rescheduling_tool.get_rescheduling_options,
            rescheduling_tool.validate_rescheduling_request
        ]
        self.ai_chat_manager.register_tools(tools)
        logger.info("All tools initialized and registered")

    async def initialize_session(self, session_id: Optional[str] = None) -> str:
        session_id = self.session_manager.create_session(session_id)
        await self.ai_chat_manager.create_chat_session(session_id)
        logger.info(f"Initialized agent session: {session_id}")
        return session_id

    async def process_message(self, session_id: str, message: str) -> str:
        try:
            if not self.session_manager.session_exists(session_id):
                raise AgentError(f"Session {session_id} not found or expired")
            
            # GET SESSION DATA FOR CONTEXT
            session_data = self.session_manager.get_session(session_id)
            
            # ENHANCED: Pass session data to AI chat manager
            response = await self.ai_chat_manager.send_message(session_id, message, session_data)
            formatted_response = self.response_formatter.format_response(response)
            
            # UPDATE SESSION CONTEXT based on user message
            self._update_session_context(session_id, message, response)
            
            logger.info(f"Processed message for session {session_id}")
            return formatted_response
        except Exception as e:
            logger.error(f"Error processing message for session {session_id}: {str(e)}")
            raise AgentError(f"Failed to process message: {str(e)}")
    
    def _update_session_context(self, session_id: str, user_message: str, ai_response: str):
        """
        Update session context based on the conversation
        """
        try:
            context_updates = {}
            
            # Track confirmation requests/responses
            if any(word in user_message.lower() for word in ['confirm', 'yes', 'proceed', 'execute']):
                context_updates['pending_confirmations'] = 'user_confirmed'
            elif any(word in user_message.lower() for word in ['cancel', 'no', 'stop']):
                context_updates['pending_confirmations'] = 'user_cancelled'
            
            # Track current discussion topic
            if 'reschedule' in user_message.lower():
                context_updates['current_discussion_topic'] = 'rescheduling'
            elif any(word in user_message.lower() for word in ['create', 'release', 'make']):
                context_updates['current_discussion_topic'] = 'order_creation'
            elif 'query' in user_message.lower() or 'show' in user_message.lower():
                context_updates['current_discussion_topic'] = 'data_query'
            
            # Update session if there are context changes
            if context_updates:
                self.session_manager.update_session(session_id, context=context_updates)
                logger.debug(f"Updated session context: {context_updates}")
                
        except Exception as e:
            logger.warning(f"Failed to update session context: {str(e)}")
            # Don't raise exception as this is non-critical

    def cleanup_session(self, session_id: str):
        self.ai_chat_manager.remove_session(session_id)
        # Session manager will clean up on its own via timeout
        logger.info(f"Cleaned up AI resources for session: {session_id}")