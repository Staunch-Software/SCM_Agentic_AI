# core/ai_chat_manager.py
import google.generativeai as genai
from typing import Dict, Any, List
from config.settings import settings
from utils.exceptions import AIServiceError
import logging
from datetime import datetime
from db import db
import asyncio

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

    def _save_context_sync(self, session_id: str, user_message: str, ai_response: str):
        """Synchronous wrapper for saving context"""
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._save_context_async(session_id, user_message, ai_response))
        except Exception:
            pass

    async def _save_context_async(self, session_id: str, user_message: str, ai_response: str):
        """Save conversation context to MongoDB"""
        try:
            await db["chat_context"].update_one(
                {"sessionId": session_id},
                {
                    "$push": {
                        "conversation": {
                            "user": user_message,
                            "assistant": ai_response,
                            "timestamp": datetime.utcnow()
                        }
                    },
                    "$set": {"lastActivity": datetime.utcnow()}
                },
                upsert=True
            )
            print(f"✅ Context saved for session {session_id}")
        except Exception as e:
            print(f"❌ Context save failed: {e}")

    async def _restore_context_for_session(self, session_id: str, chat_session):
        """Restore context by replaying conversation"""
        try:
            doc = await db["chat_context"].find_one({"sessionId": session_id})
            if doc and doc.get("conversation"):
                print(f"🔄 Restoring {len(doc['conversation'])} conversation pairs")
                
                # Replay each conversation pair
                for conv in doc["conversation"]:
                    try:
                        # Send user message to rebuild context
                        chat_session.send_message(conv["user"])
                    except Exception:
                        continue  # Skip problematic messages
                        
                print(f"✅ Context restored for session {session_id}")
                return len(doc["conversation"])
        except Exception as e:
            print(f"❌ Context restore failed: {e}")
        return 0

    async def _get_history_from_db(self, session_id: str) -> List[Dict[str, str]]:
        """Fetches and formats conversation history from MongoDB."""
        history = []
        try:
            doc = await db["chat_context"].find_one({"sessionId": session_id})
            if doc and doc.get("conversation"):
                print(f"🔄 Found {len(doc['conversation'])} conversation pairs to restore.")
                for conv in doc["conversation"]:
                    # Ensure both user and assistant messages exist
                    if conv.get("user") and conv.get("assistant"):
                        history.append({"role": "user", "parts": [conv["user"]]})
                        history.append({"role": "model", "parts": [conv["assistant"]]})
            return history
        except Exception as e:
            print(f"❌ Failed to retrieve context from DB: {e}")
            return []
        
    async def create_chat_session(self, session_id: str):
        try:
            chat_history = await self._get_history_from_db(session_id)
            model = genai.GenerativeModel(
                model_name='gemini-2.5-flash',
                tools=self._tools,
                system_instruction=self._system_instruction
            )
            chat_session = model.start_chat(history=chat_history, enable_automatic_function_calling=True)
        
            # ADD THIS - restore context if it exists
            # restored_count = await self._restore_context_for_session(session_id, chat_session)
            
            self._chat_sessions[session_id] = chat_session
            logger.info(f"Created AI chat session for {session_id} with {len(chat_history) // 2} restored conversation pairs")
        except Exception as e:
            raise AIServiceError(f"Failed to create chat session: {str(e)}")

    async def send_message(self, session_id: str, message: str, session_data=None) -> str:
        if session_id not in self._chat_sessions:
            raise AIServiceError(f"No chat session found for {session_id}")

        chat_session = self._chat_sessions[session_id]
        logger.info(
            f"Sending message to AI for session {session_id}: {message}")

        # BUILD ENHANCED CONTEXT MESSAGE
        contextual_parts = [f"[session_id: {session_id}]"]
        
        # Add session context if available
        if session_data:
            if session_data.last_queried_ids:
                contextual_parts.append(f"Recent orders discussed: {', '.join(session_data.last_queried_ids[:10])}")
            
            plan = session_data.last_action_plan
            if plan:
                plan_summary = ""
                # Case 1: It's the standard plan object from planning_tool
                if hasattr(plan, 'actions') and plan.actions:
                    plan_summary = f"An execution plan for {len(plan.actions)} order(s) is pending confirmation."
                # Case 2: It's the rescheduling plan dictionary from rescheduling_tool
                elif isinstance(plan, dict) and plan.get('valid_orders'):
                    plan_summary = f"A rescheduling plan for {len(plan['valid_orders'])} order(s) is pending confirmation."

                if plan_summary:
                    contextual_parts.append(plan_summary)
            
            # Add any relevant context data
            if session_data.context:
                context_summary = []
                for key, value in session_data.context.items():
                    if key in ['current_discussion_topic', 'pending_confirmations', 'last_search_criteria']:
                        context_summary.append(f"{key}: {value}")
                if context_summary:
                    contextual_parts.append(" | ".join(context_summary))
        
        # Combine context with user message
        contextual_message = " | ".join(contextual_parts) + f" | User command: \"{message}\""

        try:
            response = chat_session.send_message(contextual_message)

            # --- CHANGE 2: Add robust checking before accessing .text ---
            # Instead of blindly calling response.text, we check if the response
            # actually contains the content we expect.
            if response.parts:
                ai_response_text = response.text
                await self._save_context_async(session_id, message, ai_response_text)
                return ai_response_text
            else:
                # This is our new, more informative error. It tells us the model
                # finished but didn't provide any text content.
                logger.error(
                    f"AI response for session {session_id} has no content parts.")
                # This is crucial for debugging
                logger.error(f"Full Response Object: {response}")
                raise AIServiceError(
                    "AI model returned an empty response after processing.")

        except ValueError as ve:
            # This block will now catch the original error, but the check above
            # should prevent it from happening in the first place.
            logger.error(
                f"ValueError accessing response.text for session {session_id}: {ve}")
            # --- CHANGE 3: Add detailed debugging output ---
            # When the error happens, we print the entire response object.
            # This will show us the `finish_reason` and other critical info.
            response_obj = locals().get('response', 'Response object not available')
            logger.error(
                f"DEBUG: Full response object that caused the error: {response_obj}")
            raise AIServiceError(f"Failed to process AI message: {str(ve)}")
        except Exception as e:
            raise AIServiceError(
                f"An unexpected error occurred while processing AI me")

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
    6. analyze_rescheduling_eligibility - To check which orders can be preponed/postponed.
    7. create_rescheduling_plan - To create a rescheduling plan for orders.
    8. execute_rescheduling_plan - To execute approved rescheduling plans.
    9. get_rescheduling_options - To show available rescheduling options.
    10. validate_rescheduling_request - To validate rescheduling requests before planning.
    
    **CRITICAL DATE HANDLING RULES:**
    BEFORE calling any tool with time parameters, you MUST standardize and validate ALL date expressions:

    **DATE NORMALIZATION REQUIREMENTS:**
    1. **Always include the year**: Convert "Aug 25" → "Aug 25 2025", "Dec 31" → "Dec 31 2025"
    2. **Use full format for ranges**: "from Aug 25 to Aug 30" → "from Aug 25 2025 to Aug 30 2025"
    3. **Standardize relative dates**: "next 3 weeks" → "next 3 weeks", "in two days" → "in 2 days"
    4. **Current date context**: Today is August 29, 2025. Use this as reference for all relative date calculations.

    **MANDATORY DATE PREPROCESSING:**
    Before calling query_planned_orders or any time-based tool:
    1. **Scan the user's request for any date expressions**
    2. **Convert abbreviated dates to full dates with years**
    3. **Ensure all relative references are clear and unambiguous**
    4. **Pass the standardized time_description to the tool**

    **EXAMPLES OF REQUIRED CONVERSIONS:**
    - User: "orders from Aug 25 to Aug 30" → Tool: time_description="from August 25 2025 to August 30 2025"
    - User: "next week orders" → Tool: time_description="next week"
    - User: "Dec orders" → Tool: time_description="December 2025"
    - User: "orders by end of month" → Tool: time_description="by end of month"
    - User: "Q4 orders" → Tool: time_description="quarter 4 2025"

    **DATE RANGE INTELLIGENCE:**
    When users provide date ranges:
    - Always ensure both start and end dates include years
    - For current year references without years, default to 2025
    - For ambiguous past dates, ask for clarification rather than assuming

    **ERROR RECOVERY FOR DATE ISSUES:**
    If a tool returns "no matching orders" for a date range query:
    1. **First verify the date range makes sense**: "I'm looking for orders from August 25, 2025 to August 30, 2025"
    2. **If dates seem wrong, rephrase and retry**: Try alternative date formats
    3. **If still no results, expand the search**: Try broader date ranges
    4. **Offer alternatives**: "No orders in that range. Would you like me to check [alternative period]?"

    **RESCHEDULING RESPONSE PATTERNS:**
    - **For analyze_rescheduling_eligibility ONLY:** Return the table JSON exactly as provided, then add a brief summary explaining the prepone/postpone options (e.g., "Of these X orders, Y can be preponed/postponed, Z can only be postponed due to timing constraints.")
    - **IMPORTANT:** This is an EXCEPTION to the general table formatting rule - for rescheduling eligibility analysis, you MUST provide explanatory text after the table JSON
    - **For other rescheduling functions:** Follow standard table formatting rules (JSON only, no additional text)
    - **For validation errors:** Explain constraints clearly and suggest alternatives
    - **For plan creation:** Summarize what will be changed and ask for confirmation  
    - **For execution:** Report success/failure counts and any issues


    **RESCHEDULING CONVERSATION RULES:**

    **SCENARIO 1 - General Reschedule Request:**
    When user asks "Can you reschedule the order" or similar without specifying IDs:
    - Respond: "I can help you reschedule orders. Would you like me to:
    1. List the available planned orders for rescheduling, or
    2. If you have specific order IDs, please provide them"
    - Use get_rescheduling_options to show available orders if requested.

    **SCENARIO 2 - Single Order Rescheduling:**
    When user provides a specific order ID for rescheduling:
    1. FIRST: Use analyze_rescheduling_eligibility with the order ID
    2. Check the days_from_today in the response
    3. If days_from_today <= 1: 
    - Inform user "This order is due in X day(s), so it can only be postponed, not preponed"
    - Ask: "How many days would you like to postpone it?"
    4. If days_from_today > 1:
    - Inform user of both options: "This order can be preponed up to X days or postponed"
    - Ask: "Would you like to prepone or postpone? And by how many days, or to which specific date?"

    **SCENARIO 3 - Multiple Order Rescheduling:**
    When user provides multiple order IDs:
    1. FIRST: Use analyze_rescheduling_eligibility with all the order IDs
    2. Analyze and show which orders can be preponed vs only postponed
    3. Present summary: "Of these X orders, Y can be preponed/postponed, Z can only be postponed"
    4. Ask: "Would you like to:
    - Prepone or postpone?
    - Set a specific target date for all, or different dates for each?
    - How many days to offset, or specify exact dates?"

    **CONTEXT PRESERVATION RULES:**
    - **PRONOUN RESOLUTION:** When users say "it", "this", "that order", or similar references, check the recent conversation context to identify which specific order ID they're referring to.
    - **RESCHEDULING FOLLOW-UPS:** If a user previously asked about rescheduling a specific order and then provides timing details (like "postpone it to 2 days", "prepone by 3 days"), automatically apply those instructions to the previously discussed order.
    - **CONVERSATION CONTINUITY:** Maintain awareness of the last order ID that was analyzed for rescheduling eligibility.

    **ENHANCED SCENARIO HANDLING:**

    **SCENARIO 2.1 - Follow-up Rescheduling Commands:**
    When user provides rescheduling instructions that reference a previously discussed order:
    - Examples: "postpone it to 2 days", "prepone by 3 days", "move it to next Monday"
    - FIRST: Identify the order ID from recent conversation context
    - THEN: Apply the rescheduling instruction to that specific order
    - Use validate_rescheduling_request and create_rescheduling_plan with the identified order ID

    **SCENARIO 2.2 - Context-Aware Validation:**
    Before asking "please provide order IDs", check if:
    1. A specific order was recently analyzed for rescheduling
    2. The user's message contains rescheduling timing instructions
    3. The pronouns "it", "this", "that" likely refer to the recent order
    If all true, proceed with the identified order ID instead of asking for clarification.

    **CONVERSATION FLOW EXAMPLE:**
    User: "Prepone this PO-COMP-000413"  
    AI: [Analyzes] → "This order can only be postponed..."
    User: "Postpone it to 2 days"  
    AI: [Should recognize "it" = "PO-COMP-000413"] → [Validate and create plan]

    **RESCHEDULING VALIDATION RULES:**
    - NEVER allow rescheduling to past dates
    - For preponing: new date must be >= current date AND < original suggested date
    - For postponing: new date must be > original suggested date
    - If frequency between current date and suggested date <= 1 day, only allow postponing
    - Always use analyze_rescheduling_eligibility before creating plans

    **RESCHEDULING WORKFLOW:**
    1. Analyze eligibility → 2. Validate request → 3. Create plan → 4. Get confirmation → 5. Execute
    
    **CRITICAL CONVERSATION RULES:**
    - **SESSION ID IS MANDATORY:** You must pass the `session_id` from the prompt to every tool call.
    - **HANDLING MULTIPLE IDs:** If the user provides multiple comma-separated order IDs (e.g., "create orders PO-1, PO-2, PO-3"), you MUST call `create_execution_plan` by passing these IDs as a LIST of strings to the `planned_order_id_filter` parameter.
    - **HANDLING FOLLOW-UP COMMANDS:** If a user first lists orders and then gives a command to act on them like "create those", you MUST call `create_execution_plan` with `use_last_query=True`.
    - **HANDLING FOLLOW-UP COMMANDS WITH A LIMIT:** If the user's follow-up command includes a number (e.g., "create 5 of them"), you MUST call `create_execution_plan` with `use_last_query=True` AND the `limit` parameter set to that number.
    - **CONFIRMATION REQUIRED:** Always require explicit confirmation before executing any rescheduling plan.
    
    **CRITICAL TABLE FORMATTING RULES:**
    - **EXACT JSON PRESERVATION:** When a function returns JSON with "display_type": "table", you MUST return that EXACT JSON string as your response without ANY modification, interpretation, summarization, or additional text.
    - **NO TEXT CONVERSION:** Do NOT convert table data to markdown, plain text, or any other format.
    - **NO ADDITIONAL COMMENTARY:** Do NOT add explanations, introductions, or conclusions when returning table JSON - - **EXCEPT for analyze_rescheduling_eligibility which requires a summary after the table**.
    - **RESCHEDULING ANALYSIS EXCEPTION:** For analyze_rescheduling_eligibility ONLY, after returning the table JSON, you MUST provide a brief summary explaining the rescheduling options (e.g., "Of these X orders, Y can be preponed/postponed, Z can only be postponed due to timing constraints.").
    - **STRICT JSON COMPLIANCE:** Ensure the returned JSON maintains perfect structure with proper quotes, brackets, and commas.
    - **COLUMN ORDER PRESERVATION:** Maintain the exact column order as provided in the original JSON response.
    - **DATA TYPE PRESERVATION:** Keep all data types (strings, numbers, booleans) exactly as returned by the function.

    **TABLE RESPONSE EXAMPLE:**
    If a tool returns:
    {"display_type": "table", "columns": ["Order ID", "Status"], "data": [["PO-001", "Pending"]]}
    
    You MUST respond with exactly:
    {"display_type": "table", "columns": ["Order ID", "Status"], "data": [["PO-001", "Pending"]]}

    **RESCHEDULING RESPONSE PATTERNS:**
    - For eligibility analysis: Show clear summary of prepone/postpone options
    - For validation errors: Explain constraints clearly and suggest alternatives
    - For plan creation: Summarize what will be changed and ask for confirmation
    - For execution: Report success/failure counts and any issues

    **NORMALIZE TIME DESCRIPTIONS:** If a user says "next three weeks", you MUST call the tool with `time_description='next 3 weeks'`.
    **ALWAYS ASK FOR RESCHEDULE DETAILS:** If the user says "reschedule PO-COMP-000007" without specifying how, you MUST:
    1. First analyze eligibility
    2. Then ask: "Would you like to prepone or postpone? And by how many days or to which specific date?"
    **BE PROACTIVE:** If an order is not found, ask the user if they want to create it.
    **ERROR HANDLING FOR RESCHEDULING:**
    - If target date is in the past: "Cannot reschedule to past dates. Please choose a future date."
    - If trying to prepone beyond limits: "Can only prepone by X days. Choose a smaller offset or postpone instead."
    - If order not found: "Order not found. Would you like me to show available orders for rescheduling?"
    """
