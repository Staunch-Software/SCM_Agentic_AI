# utils/data_formatter.py
import pandas as pd
import json

class DataFormatter:
    def format_planned_orders(self, df: pd.DataFrame, reschedule_needed: bool = False) -> str:
        """Formats planned orders DataFrame into a structured JSON string."""
        if reschedule_needed:
            # CORRECTED: Changed 'item_name' to 'item'
            cols = ['planned_order_id', 'item', 'suggested_due_date', 'reschedule_out_days']
            title = "PLANNED orders to reschedule:"
        else:
            # CORRECTED: Changed 'item_name' to 'item'
            cols = ['planned_order_id', 'item', 'quantity', 'suggested_due_date', 'item_type']
            title = "Here are the PLANNED orders I found in the local file:"
        
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
        """Formats Odoo orders DataFrame into a structured JSON string with clean headers."""
        # Select the columns using their technical names
        cols = ['display_name', 'x_studio_planned_order_id', 'type', 'schedule_date', 'state']
        df_display = df[cols].copy()

        # --- THIS IS THE FIX ---
        # Rename the columns to be more user-friendly for the final display
        df_display.rename(columns={
            'display_name': 'Display Name',
            'x_studio_planned_order_id': 'Planned Order Id',
            'type': 'Type',
            'schedule_date': 'Schedule Date',
            'state': 'State'
        }, inplace=True)
        # --- END OF FIX ---

        # The date might contain a time component, so we'll clean it up for display
        if 'Schedule Date' in df_display.columns:
            df_display['Schedule Date'] = pd.to_datetime(df_display['Schedule Date']).dt.strftime('%Y-%m-%d')

        table_data = {
            "display_type": "table",
            "title": "Here are the orders I found in Odoo:",
            "headers": df_display.columns.tolist(), # This will now use the new, clean names
            "rows": df_display.to_dict('records')
        }
        
        return json.dumps(table_data)