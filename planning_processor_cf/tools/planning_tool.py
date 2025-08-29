# tools/planning_tool.py
from typing import Optional, List
from .base_tool import BaseTool
from services.planning_service import PlanningService

class PlanningTool(BaseTool):
    def __init__(self, planning_service: PlanningService, session_manager):
        super().__init__(session_manager)
        self.planning_service = planning_service

    def create_execution_plan(self, session_id: str, scenario: str, time_description: Optional[str] = None, 
                              # --- THIS IS THE FIX ---
                              planned_order_id_filter: Optional[List[str]] = None, 
                              # --- END OF FIX ---
                              limit: Optional[int] = None, item_type_filter: Optional[str] = None, 
                              reschedule_duration: Optional[str] = None, use_last_query: bool = False) -> str:
        self.log_tool_execution("create_execution_plan", session_id, scenario=scenario, time_description=time_description, planned_order_id_filter=planned_order_id_filter, limit=limit, item_type_filter=item_type_filter, use_last_query=use_last_query)
        try:
            session_data = self.session_manager.get_session(session_id)
            
            action_plan = self.planning_service.create_plan(
                scenario=scenario,
                last_queried_ids=session_data.last_queried_ids,
                time_description=time_description,
                planned_order_id_filter=planned_order_id_filter,
                limit=limit,
                item_type_filter=item_type_filter,
                reschedule_duration=reschedule_duration,
                use_last_query=use_last_query
            )

            if not action_plan.actions:
                return self.format_empty_response("No orders match your criteria to create a plan")

            self.session_manager.update_session(session_id, last_action_plan=action_plan)
            return self.format_success_response(f"I have created a plan with {len(action_plan.actions)} action(s).")
        except Exception as e:
            return self.format_error_response(f"Failed to create plan: {str(e)}")