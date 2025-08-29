# services/planning_service.py
from typing import List, Dict, Any, Optional
import pandas as pd
from services.data_service import DataService
from services.odoo_service import OdooService
from utils.time_parser import TimeParser
from models.session_models import ActionPlan
from utils.exceptions import PlanningError
import logging

logger = logging.getLogger(__name__)

class PlanningService:
    def __init__(self, data_service: DataService, odoo_service: OdooService):
        self.data_service = data_service
        self.odoo_service = odoo_service
        self.time_parser = TimeParser()

    def create_plan(self, scenario: str, last_queried_ids: Optional[List[str]], **kwargs) -> ActionPlan:
        try:
            df_enriched = self.data_service.load_data()
            orders_to_action = pd.DataFrame()

            if kwargs.get('use_last_query'):
                if not last_queried_ids:
                    raise PlanningError("Cannot use last query because no orders are in memory.")
                orders_to_action = df_enriched[df_enriched['planned_order_id'].isin(last_queried_ids)]
                orders_to_action['planned_order_id'] = pd.Categorical(orders_to_action['planned_order_id'], categories=last_queried_ids, ordered=True)
                orders_to_action = orders_to_action.sort_values('planned_order_id')
            elif kwargs.get('planned_order_id_filter'):
                id_filter = kwargs['planned_order_id_filter']
                orders_to_action = df_enriched[df_enriched['planned_order_id'].isin(id_filter)]
            elif scenario == "firm_release" and kwargs.get('time_description'):
                orders_to_action = self.time_parser.filter_dataframe_by_time(
                    df_enriched, kwargs['time_description'], date_column='suggested_due_date'
                )
            else:
                raise PlanningError("To create a plan, you must provide a time description, specific order IDs, or use the last query.")

            # --- THIS IS THE FIX ---
            # Standardize the filter to use "Purchase" and "Manufacture".
            if kwargs.get('item_type_filter'):
                item_type = kwargs['item_type_filter'].lower()
                if item_type in ['purchase', 'manufacture']:
                     orders_to_action = orders_to_action[orders_to_action['item_type'].str.lower() == item_type]
            # --- END OF FIX ---

            if orders_to_action.empty:
                return ActionPlan(actions=[])

            limit = kwargs.get('limit')
            if limit is not None:
                try:
                    limit_int = int(limit)
                    if limit_int > 0:
                        orders_to_action = orders_to_action.head(limit_int)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid limit value received: '{limit}'. Ignoring limit.")

            actionable_orders = []
            for _, row in orders_to_action.iterrows():
                row_dict = row.to_dict()
                row_dict['suggested_due_date'] = row['suggested_due_date'].strftime('%Y-%m-%d')
                action_type = "reschedule" if scenario == "reschedule" else "create"
                if action_type == "reschedule" and kwargs.get('reschedule_duration'):
                    row_dict['user_defined_reschedule_days'] = self.time_parser.parse_duration_to_days(kwargs['reschedule_duration'])
                actionable_orders.append({"action_type": action_type, "order_data": row_dict})
            
            return ActionPlan(actions=actionable_orders)
        except Exception as e:
            logger.error(f"Failed to create plan: {e}")
            raise PlanningError(f"Failed to create plan: {str(e)}")

    def execute_plan(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for action in actions:
            try:
                order_data = action.get("order_data", {})
                action_type = action.get("action_type")
                if action_type == "create":
                    # --- THIS IS THE FIX ---
                    # Check for "Manufacture" instead of "Make".
                    if order_data.get("item_type") == "Manufacture":
                        result = self.odoo_service.create_manufacturing_order(order_data)
                    else: # Assumes anything else is a Purchase
                        result = self.odoo_service.create_purchase_order(order_data)
                    # --- END OF FIX ---
                else:
                    result = {"status": "skipped", "message": "Unknown action type"}
                results.append(result)
            except Exception as e:
                logger.error(f"Error executing action for {order_data.get('planned_order_id', 'N/A')}: {str(e)}")
                results.append({
                    "status": "error",
                    "message": f"Failed for {order_data.get('planned_order_id', 'N/A')}: {str(e)}"
                })
        return results