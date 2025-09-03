# tools/execution_tool.py
import json
from .base_tool import BaseTool
from services.planning_service import PlanningService
import logging

logger = logging.getLogger(__name__)

class ExecutionTool(BaseTool):
    def __init__(self, planning_service: PlanningService, session_manager):
        super().__init__(session_manager)
        self.planning_service = planning_service

    def execute_plan(self, session_id: str) -> str:
        self.log_tool_execution("execute_plan", session_id)
        try:
            session_data = self.session_manager.get_session(session_id)
            plan_to_execute = session_data.last_action_plan

            if not plan_to_execute:
                return self.format_error_response("There is no action plan to execute. Please create a plan first.")

            # ============================================================
            # START OF THE CORRECTED LOGIC
            # ============================================================
            # We must check for the object attribute *first* before checking the dictionary key.
            
            # Case 1: It's a standard execution plan (an object with .actions)
            if hasattr(plan_to_execute, 'actions'):
                if not plan_to_execute.actions:
                    return self.format_error_response("The action plan is empty.")
                
                logger.info("Detected a standard execution plan. Executing...")
                results = self.planning_service.execute_plan(plan_to_execute.actions)
                success_count = len([r for r in results if r.get('status') == 'success'])
                summary = f"Execution complete. Successfully processed {success_count}/{len(results)} action(s)."

            # Case 2: It's a rescheduling plan (a dictionary with 'valid_orders')
            elif isinstance(plan_to_execute, dict) and 'valid_orders' in plan_to_execute:
                logger.info("Detected a rescheduling plan. Executing...")
                valid_orders = plan_to_execute.get('valid_orders', [])
                if not valid_orders:
                    return self.format_error_response("No valid orders to reschedule in the current plan.")
                
                results = self.planning_service.execute_reschedule_actions(valid_orders)
                success_count = len([r for r in results if r.get('status') == 'success'])
                summary = f"Rescheduling complete. Successfully rescheduled {success_count}/{len(results)} order(s)."

            # Case 3: Unknown plan type
            else:
                logger.error(f"Unknown plan type in session {session_id}: {type(plan_to_execute)}")
                return self.format_error_response("An unknown or invalid plan was found in the session.")
            # ============================================================
            # END OF THE CORRECTED LOGIC
            # ============================================================

            self.session_manager.update_session(session_id, last_action_plan=None)

            failed_count = len(results) - success_count
            if failed_count > 0:
                summary += f" {failed_count} action(s) failed. Please review the errors."
            
            return json.dumps({"summary": summary, "results": results})

        except Exception as e:
            logger.error(f"Failed to execute plan for session {session_id}: {e}", exc_info=True)
            return self.format_error_response(f"Failed to execute plan: {str(e)}")