# utils/data_formatter.py
import pandas as pd
import json

class DataFormatter:
    def format_planned_orders(self, df: pd.DataFrame, reschedule_needed: bool = False) -> str:
        if reschedule_needed:
            cols = ['planned_order_id', 'item_name', 'suggested_due_date', 'reschedule_out_days']
            title = "PLANNED orders to reschedule:"
        else:
            cols = ['planned_order_id', 'item_name', 'quantity', 'suggested_due_date', 'item_type']
            title = "PLANNED orders I found in the local file:"
        
        df_display = df[cols].copy()
        df_display['suggested_due_date'] = pd.to_datetime(df_display['suggested_due_date']).dt.strftime('%Y-%m-%d')
        
       # Convert DataFrame to the structured dictionary format
        table_data = {
            "display_type": "table",
            "title": title,
            "headers": df_display.columns.tolist(),
            "rows": df_display.to_dict('records')
        }
        
        return json.dumps(table_data)

    def format_odoo_orders(self, df: pd.DataFrame) -> str:
        cols = ['display_name', 'x_planned_order_id', 'type', 'schedule_date', 'state']
        df_display = df[cols].copy()
         # Convert DataFrame to the structured dictionary format
        table_data = {
            "display_type": "table",
            "title": "Here are the orders I found in Odoo:",
            "headers": df_display.columns.tolist(),
            "rows": df_display.to_dict('records')
        }
        
        return json.dumps(table_data)