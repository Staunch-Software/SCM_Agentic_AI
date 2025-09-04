# tools/supplier_tool.py
from tools.base_tool import BaseTool
from services.planning_service import PlanningService
from core.session_manager import SessionManager
from pydantic import BaseModel, Field
from typing import Dict, Any

class CreateSupplierAndRetryToolInput(BaseModel):
    session_id: str = Field(...)
    supplier_name: str = Field(description="The name of the supplier to create in Odoo.")
    original_action: Dict[str, Any] = Field(description="The original action dictionary that failed, which contains the order data.")

class CreateSupplierAndRetryTool(BaseTool):
    name = "create_supplier_and_retry"
    description = "Creates a new supplier in Odoo and immediately retries the previously failed purchase order creation. Use this only after the user confirms the supplier creation."
    args_schema = CreateSupplierAndRetryToolInput

    def __init__(self, planning_service: PlanningService, session_manager: SessionManager, **kwargs):
        super().__init__(session_manager=session_manager, **kwargs)
        self.planning_service = planning_service
        self.session_manager = session_manager

    def create_supplier_and_retry(self, session_id: str, supplier_name: str, original_action: Dict[str, Any], **kwargs):
        # This tool directly calls the new service method
        results = self.planning_service.create_supplier_and_retry_action(
            supplier_name=supplier_name,
            original_action=original_action
        )
        # Clear the plan after the execution attempt is complete
        self.session_manager.update_session(session_id, last_action_plan=None)
        return results