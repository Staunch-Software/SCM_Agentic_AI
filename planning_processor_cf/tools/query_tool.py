# tools/query_tool.py
from typing import Optional

import pandas as pd

from utils.exceptions import TimeParsingError
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
            
            # --- THIS IS THE FIX ---
            # Standardize the filter to use "Purchase" and "Manufacture" to match your CSV data.
            if item_type and item_type.lower() in ['purchase', 'manufacture']:
                df = df[df['item_type'].str.lower() == item_type.lower()]
            # --- END OF FIX ---

            if reschedule_needed is True:
                df = df[df['reschedule_out_days'] > 0]

            if df.empty:
                self.session_manager.update_session(session_id, last_queried_ids=None)
                return self.format_empty_response("I found no planned orders matching your criteria")

            self.session_manager.update_session(session_id, last_queried_ids=df['planned_order_id'].tolist())

            if query_type.lower() == "count":
                return self.format_success_response(f"I found {len(df)} planned orders matching your criteria")

            cols_to_display = ['planned_order_id', 'item', 'quantity', 'suggested_due_date', 'item_type']
            if reschedule_needed:
                cols_to_display = ['planned_order_id', 'item', 'suggested_due_date', 'reschedule_out_days']
            
            df_display = df[cols_to_display].copy()
            df_display['suggested_due_date'] = df_display['suggested_due_date'].dt.strftime('%Y-%m-%d')
            
            with pd.option_context('display.width', 1000, 'display.max_rows', None):
                table = df_display.to_string(index=False)
            df = df.sort_values(by='suggested_due_date')
            # formatted_result = f"Here are the PLANNED orders I found in the local file:\n{table}"
            formatted_result = self.data_formatter.format_planned_orders(df, reschedule_needed)
            return self.format_success_response(formatted_result)
        except Exception as e:
            return self.format_error_response(f"An error occurred while querying local data: {str(e)}")

    
    def query_planned_orders_natural(self, session_id: str, natural_query: str) -> str:
        """
        New method for processing complete natural language queries.
        Parses the query and extracts all parameters automatically.
        
        Examples:
        - "Show me make orders due before Christmas"
        - "What orders are overdue?"
        - "How many buy orders are due next week?"
        - "Orders between Dec 1 and 15 that need rescheduling"
        """
        self.log_tool_execution("query_planned_orders_natural", session_id, natural_query=natural_query)
        
        try:
            # Extract parameters from natural language query
            params = self.time_parser.extract_query_parameters(natural_query)
            
            # Call the main query method with extracted parameters
            return self.query_planned_orders(
                session_id=session_id,
                time_description=params.get('time_description'),
                item_type=params.get('item_type'),
                query_type=params.get('query_type', 'list'),
                reschedule_needed=params.get('reschedule_needed')
            )
            
        except Exception as e:
            return self.format_error_response(f"Could not process natural language query: {str(e)}")

    def query_orders_with_clarification(self, session_id: str, query: str) -> str:
        """
        Query method with built-in clarification for ambiguous queries.
        Will attempt to parse the query and ask for clarification if needed.
        """
        try:
            # First, try to process as natural language
            return self.query_planned_orders_natural(session_id, query)
            
        except TimeParsingError as e:
            # If time parsing fails, provide clarification options
            return self._generate_clarification_response(query, str(e))
        except Exception as e:
            return self.format_error_response(f"Error processing query: {str(e)}")

    def _generate_clarification_response(self, original_query: str, error_msg: str) -> str:
        """Generate a helpful clarification response for ambiguous queries"""
        clarification_data = {
            "needs_clarification": True,
            "original_query": original_query,
            "error": error_msg,
            "suggestions": [
                "Try specifying a date range like 'between Jan 1 and Jan 15'",
                "Use relative dates like 'next week' or 'in 30 days'",
                "Specify comparison dates like 'before December 25' or 'after next Friday'",
                "For overdue items, use words like 'overdue', 'late', or 'past due'",
                "Examples: 'make orders due tomorrow', 'buy orders overdue', 'orders this month'"
            ]
        }
        return self.format_success_response(clarification_data)

    def get_supported_time_expressions(self) -> str:
        """
        Return documentation of supported time expressions for user reference.
        """
        documentation = {
            "supported_expressions": {
                "basic_references": [
                    "today", "tomorrow", "yesterday", "day after tomorrow"
                ],
                "relative_periods": [
                    "this week", "next week", "last week",
                    "this month", "next month", "last month",
                    "in 30 days", "2 weeks from now", "next 10 days"
                ],
                "comparison_queries": [
                    "before December 25", "after next Friday", "on or before month end",
                    "by Christmas", "until next week", "since last month"
                ],
                "range_queries": [
                    "between Dec 1 and 15", "from Monday to Friday",
                    "Jan 1 to Jan 31", "next week through month end"
                ],
                "specific_dates": [
                    "December 25, 2024", "Jan 1st", "2024-12-15",
                    "12/25/2024", "25-12-2024"
                ],
                "business_periods": [
                    "month end", "quarter end", "year end", "fiscal year end",
                    "beginning of month", "end of quarter"
                ],
                "fuzzy_references": [
                    "around next week", "roughly end of month", "sometime this month",
                    "approximately Christmas", "about 2 weeks from now"
                ],
                "overdue_patterns": [
                    "overdue", "late", "past due", "behind schedule", "delayed"
                ]
            },
            "combination_examples": [
                "make orders due before Christmas",
                "buy orders overdue that need rescheduling",
                "orders between Dec 1 and 15",
                "how many orders are due next week",
                "make items roughly end of month"
            ]
        }
        return self.format_success_response(documentation)