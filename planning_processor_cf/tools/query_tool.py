# tools/query_tool.py
from typing import Optional
from .base_tool import BaseTool
from services.data_service import DataService
from utils.time_parser import TimeParser
from utils.data_formatter import DataFormatter

class QueryTool(BaseTool):
    def __init__(self, data_service: DataService, session_manager):
        super().__init__(session_manager)
        self.data_service = data_service
        self.time_parser = TimeParser()
        self.data_formatter = DataFormatter()

    def query_planned_orders(self, session_id: str, time_description: Optional[str] = None, item_type: Optional[str] = None, query_type: str = "list", reschedule_needed: Optional[bool] = None) -> str:
        self.log_tool_execution("query_planned_orders", session_id, time_description=time_description, item_type=item_type, query_type=query_type, reschedule_needed=reschedule_needed)
        try:
            df = self.data_service.load_data()
            
            if time_description:
                df = self.time_parser.filter_dataframe_by_time(df, time_description, date_column='suggested_due_date')
            if item_type and item_type.lower() in ['make', 'buy']:
                df = df[df['item_type'].str.lower() == item_type.lower()]
            if reschedule_needed is True:
                df = df[df['reschedule_out_days'] > 0]

            if df.empty:
                self.session_manager.update_session(session_id, last_queried_ids=None)
                return self.format_empty_response("I found no planned orders matching your criteria")

            self.session_manager.update_session(session_id, last_queried_ids=df['planned_order_id'].tolist())

            if query_type.lower() == "count":
                return self.format_success_response(f"I found {len(df)} planned orders matching your criteria")

            formatted_result = self.data_formatter.format_planned_orders(df, reschedule_needed)
            return self.format_success_response(formatted_result)
        except Exception as e:
            return self.format_error_response(f"An error occurred while querying local data: {str(e)}")