# tools/execution_tool.py
import json
from .base_tool import BaseTool
from services.planning_service import PlanningService

class ExecutionTool(BaseTool):
    def __init__(self, planning_service: PlanningService, session_manager):
        super().__init__(session_manager)
        self.planning_service = planning_service

    def execute_plan_in_odoo(self, session_id: str) -> str:
        self.log_tool_execution("execute_plan_in_odoo", session_id)
        try:
            session_data = self.session_manager.get_session(session_id)
            action_plan = session_data.last_action_plan

            if not action_plan or not action_plan.actions:
                return self.format_error_response("There is no action plan to execute")

            results = self.planning_service.execute_plan(action_plan.actions)
            self.session_manager.update_session(session_id, last_action_plan=None)

            success_count = len([r for r in results if r.get('status') == 'success'])
            failed_count = len(results) - success_count
            summary = f"Execution complete. Successfully processed {success_count}/{len(results)} action(s)."
            if failed_count > 0:
                summary += f" {failed_count} action(s) failed. Please review the errors."
            
            return json.dumps({"summary": summary, "results": results})
        except Exception as e:
            return self.format_error_response(f"Failed to execute plan: {str(e)}")