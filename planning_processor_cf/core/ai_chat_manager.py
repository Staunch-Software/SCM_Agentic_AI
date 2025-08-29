# core/ai_chat_manager.py
import google.generativeai as genai
from typing import Dict, Any, List
from config.settings import settings
from utils.exceptions import AIServiceError
import logging

logger = logging.getLogger(__name__)

class AIChatManager:
    def __init__(self):
        self._chat_sessions: Dict[str, Any] = {}
        self._tools: List = []
        self._system_instruction = self._get_system_instruction()
        self._initialize_genai()

    def _initialize_genai(self):
        try:
            genai.configure(api_key=settings.gemini_api_key)
            logger.info("Google Generative AI initialized successfully")
        except Exception as e:
            raise AIServiceError(f"Failed to initialize Gemini AI: {str(e)}")

    def register_tools(self, tools: list):
        self._tools = tools
        logger.info(f"Registered {len(tools)} tools for AI model")

    def create_chat_session(self, session_id: str):
        try:
            model = genai.GenerativeModel(
                model_name='gemini-2.5-flash',
                tools=self._tools,
                system_instruction=self._system_instruction
            )
            self._chat_sessions[session_id] = model.start_chat(enable_automatic_function_calling=True)
            logger.info(f"Created AI chat session for {session_id}")
        except Exception as e:
            raise AIServiceError(f"Failed to create chat session: {str(e)}")

    def send_message(self, session_id: str, message: str) -> str:
        if session_id not in self._chat_sessions:
            raise AIServiceError(f"No chat session found for {session_id}")
        try:
            chat_session = self._chat_sessions[session_id]
            logger.info(f"Sending message to AI for session {session_id}: {message}")
            
            # Inject session_id into the prompt for tools to use
            contextual_message = f"[session_id: {session_id}] User command: \"{message}\""
            
            response = chat_session.send_message(contextual_message)
            return response.text
        except Exception as e:
            raise AIServiceError(f"Failed to process AI message: {str(e)}")

    def remove_session(self, session_id: str):
        if session_id in self._chat_sessions:
            del self._chat_sessions[session_id]
            logger.info(f"Removed AI chat session for {session_id}")

    def _get_system_instruction(self) -> str:
        """
        Centralizes the main system prompt for the AI.
        This defines the agent's personality, rules, and capabilities.
        """
        return """
        You are a master supply chain planning assistant. Your personality is helpful, precise, and proactive.
        You MUST inject the session_id, which is provided in the user prompt like `[session_id: xxxx]`, into every tool call that requires it.

        **TOOL CHEAT SHEET:**
        1. query_planned_orders - For questions about potential work from the local CSV file.
        2. get_odoo_order_details - For questions about orders already created in Odoo.
        3. check_order_status_in_odoo - To verify if a specific order ID exists in Odoo.
        4. create_execution_plan - When a user gives a command to create, release, or reschedule orders.
        5. execute_plan_in_odoo - For executing a plan after the user gives their final confirmation.

        **CRITICAL CONVERSATION RULES:**
        - **SESSION ID IS MANDATORY:** You must pass the `session_id` from the prompt to every tool call.
        - **HANDLING MULTIPLE IDs:** If the user provides multiple comma-separated order IDs (e.g., "create orders PO-1, PO-2, PO-3"), you MUST call `create_execution_plan` by passing these IDs as a LIST of strings to the `planned_order_id_filter` parameter.
        - **HANDLING FOLLOW-UP COMMANDS:** If a user first lists orders and then gives a command to act on them like "create those", you MUST call `create_execution_plan` with `use_last_query=True`.
        - **HANDLING FOLLOW-UP COMMANDS WITH A LIMIT:** If the user's follow-up command includes a number (e.g., "create 5 of them"), you MUST call `create_execution_plan` with `use_last_query=True` AND the `limit` parameter set to that number.
        - **PRESENTATION IS KEY:** When a tool returns tabular data, present it exactly as-is inside a markdown code block.
        - **NORMALIZE TIME DESCRIPTIONS:** If a user says "next three weeks", you MUST call the tool with `time_description='next 3 weeks'`.
        - **ALWAYS ASK FOR RESCHEDULE DURATION:** If the user says "reschedule PO-COMP-000007", you MUST respond with "Certainly. By how long should I reschedule it? (e.g., 5 days, 2 weeks)".
        - **BE PROACTIVE:** If an order is not found, ask the user if they want to create it.
        """