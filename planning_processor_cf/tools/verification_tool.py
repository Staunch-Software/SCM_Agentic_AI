# tools/verification_tool.py
import json
from .base_tool import BaseTool
from .odoo_query_tool import OdooQueryTool
from services.odoo_service import OdooService

class VerificationTool(BaseTool):
    def __init__(self, odoo_service: OdooService, session_manager):
        super().__init__(session_manager)
        self.odoo_query_tool = OdooQueryTool(odoo_service, session_manager)

    def check_order_status_in_odoo(self, planned_order_id: str, session_id: str) -> str:
        self.log_tool_execution("check_order_status_in_odoo", session_id, planned_order_id=planned_order_id)
        try:
            result_json = self.odoo_query_tool.get_odoo_order_details(
                planned_order_id=planned_order_id,
                session_id=session_id
            )
            result = json.loads(result_json)
            if "error" in result or "could not find" in result.get("result", "").lower():
                return json.dumps({
                    "status": "not_found",
                    "message": f"No, I could not find any order in Odoo for planned order ID {planned_order_id}."
                })
            else:
                return json.dumps({
                    "status": "found",
                    "message": f"Yes, I found the following order in Odoo:\n{result['result']}"
                })
        except Exception as e:
            return self.format_error_response(f"An error occurred while checking Odoo: {str(e)}")