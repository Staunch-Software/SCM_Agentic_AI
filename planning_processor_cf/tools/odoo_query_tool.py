# tools/odoo_query_tool.py
from typing import Optional
import pandas as pd
from .base_tool import BaseTool
from services.odoo_service import OdooService
from utils.time_parser import TimeParser
from utils.data_formatter import DataFormatter

class OdooQueryTool(BaseTool):
    def __init__(self, odoo_service: OdooService, session_manager):
        super().__init__(session_manager)
        self.odoo_service = odoo_service
        self.time_parser = TimeParser()
        self.data_formatter = DataFormatter()

    def get_odoo_order_details(self, session_id: str, planned_order_id: Optional[str] = None, item_type: Optional[str] = None, time_description: Optional[str] = None) -> str:
        self.log_tool_execution("get_odoo_order_details", session_id, planned_order_id=planned_order_id, item_type=item_type, time_description=time_description)
        try:
            results = []
            base_domain = [['x_planned_order_id', '!=', False]]
            if planned_order_id:
                base_domain.append(['x_planned_order_id', '=', planned_order_id])

            if not item_type or item_type.lower() == 'make':
                results.extend(self.odoo_service.get_production_orders(domain=base_domain))
            if not item_type or item_type.lower() == 'buy':
                results.extend(self.odoo_service.get_purchase_orders(domain=base_domain))

            if not results:
                return self.format_empty_response("I could not find any orders in Odoo matching your criteria")

            df = pd.DataFrame(results)
            if time_description:
                df = self.time_parser.filter_dataframe_by_time(df, time_description, date_column='schedule_date')
            
            if df.empty:
                return self.format_empty_response("I found orders in Odoo, but none that match your time criteria")

            formatted_result = self.data_formatter.format_odoo_orders(df)
            return self.format_success_response(formatted_result)
        except Exception as e:
            return self.format_error_response(f"An error occurred while querying Odoo: {str(e)}")