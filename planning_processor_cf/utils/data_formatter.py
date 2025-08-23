# utils/data_formatter.py
import pandas as pd

class DataFormatter:
    def format_planned_orders(self, df: pd.DataFrame, reschedule_needed: bool = False) -> str:
        if reschedule_needed:
            cols = ['planned_order_id', 'item_name', 'suggested_due_date', 'reschedule_out_days']
        else:
            cols = ['planned_order_id', 'item_name', 'quantity', 'suggested_due_date', 'item_type']
        
        df_display = df[cols].copy()
        df_display['suggested_due_date'] = pd.to_datetime(df_display['suggested_due_date']).dt.strftime('%Y-%m-%d')
        
        with pd.option_context('display.width', 1000, 'display.max_rows', None):
            table = df_display.to_string(index=False)
        return f"Here are the PLANNED orders I found in the local file:\n{table}"

    def format_odoo_orders(self, df: pd.DataFrame) -> str:
        cols = ['display_name', 'x_planned_order_id', 'type', 'schedule_date', 'state']
        df_display = df[cols].copy()
        with pd.option_context('display.width', 1000, 'display.max_rows', None):
            table = df_display.to_string(index=False)
        return f"Here are the orders I found in Odoo:\n{table}"