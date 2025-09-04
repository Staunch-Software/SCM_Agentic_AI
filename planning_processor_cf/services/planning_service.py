# services/planning_service.py
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, date
from services.data_service import DataService
from services.odoo_service import OdooService
from utils.time_parser import TimeParser
from models.session_models import ActionPlan
from utils.exceptions import PlanningError, OdooOperationError
import logging
import re

logger = logging.getLogger(__name__)

class PlanningService:
    def __init__(self, data_service: DataService, odoo_service: OdooService):
        self.data_service = data_service
        self.odoo_service = odoo_service
        self.time_parser = TimeParser()

    ODOO_CUSTOM_FIELD_NAME = 'x_studio_planned_order_id'

    def create_plan(self, scenario: str, last_queried_ids: Optional[List[str]], **kwargs) -> ActionPlan:
        try:
            df_enriched = self.data_service.load_data()
            orders_to_action = pd.DataFrame()

            # --- THIS IS THE FIX ---
            # The service now correctly handles a list of IDs.
            if kwargs.get('planned_order_id_filter'):
                id_filter = kwargs['planned_order_id_filter']
                # Use .isin() for filtering with a list
                orders_to_action = df_enriched[df_enriched['planned_order_id'].isin(id_filter)]
                if orders_to_action.empty:
                    raise PlanningError(f"IDs '{id_filter}' not found in local file")
            # --- END OF FIX ---
            elif kwargs.get('use_last_query'):
                if not last_queried_ids:
                    raise PlanningError("Cannot use last query because no orders are in memory.")
                orders_to_action = df_enriched[df_enriched['planned_order_id'].isin(last_queried_ids)]
                orders_to_action['planned_order_id'] = pd.Categorical(orders_to_action['planned_order_id'], categories=last_queried_ids, ordered=True)
                orders_to_action = orders_to_action.sort_values('planned_order_id')
            elif scenario == "firm_release" and kwargs.get('time_description'):
                orders_to_action = self.time_parser.filter_dataframe_by_time(
                    df_enriched, kwargs['time_description'], date_column='suggested_due_date'
                )
            else:
                raise PlanningError("To create a plan, you must provide a time description, specific order IDs, or use the last query.")

            if kwargs.get('item_type_filter'):
                item_type = kwargs['item_type_filter'].lower()
                if item_type in ['purchase', 'manufacture']:
                     orders_to_action = orders_to_action[orders_to_action['item_type'].str.lower() == item_type]

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

            orders_to_action = self._overwrite_supplier_from_rankings(orders_to_action)
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
                order_data = action.get("order_data", {})
                planned_order_id = order_data.get('planned_order_id', 'N/A')
                try:
                    action_type = action.get("action_type")
                    if action_type == "create":
                        if order_data.get("item_type") == "Manufacture":
                            result = self.odoo_service.create_manufacturing_order(order_data)
                        else: # Assumes anything else is a Purchase
                            result = self.odoo_service.create_purchase_order(order_data)
                    else:
                        result = {"status": "skipped", "message": "Unknown action type"}
                    results.append(result)
                
                except OdooOperationError as e:
                    error_message = str(e)
                    logger.warning(f"Odoo operation failed for {planned_order_id}: {error_message}")
                    
                    # Check for the specific "Supplier not found" error
                    if "Supplier" in error_message and "not found" in error_message:
                        # Use regex to safely extract the supplier name
                        match = re.search(r"Supplier '(.*?)' not found", error_message)
                        if match:
                            supplier_name = match.group(1)
                            # Return a structured response for the AI to handle
                            results.append({
                                "status": "requires_user_action",
                                "action_type": "create_supplier_and_retry",
                                "message": f"Supplier '{supplier_name}' not found. Proposing creation.",
                                "data": {
                                    "supplier_to_create": supplier_name,
                                    "original_action": action
                                }
                            })
                        else:
                            # Fallback for unexpected error format
                            results.append({"status": "error", "message": f"Failed for {planned_order_id}: {error_message}"})
                    else:
                        # Handle all other Odoo errors
                        results.append({"status": "error", "message": f"Failed for {planned_order_id}: {error_message}"})

                except Exception as e:
                    logger.error(f"Generic error executing action for {planned_order_id}: {e}", exc_info=True)
                    results.append({
                        "status": "error",
                        "message": f"An unexpected error occurred for {planned_order_id}: {str(e)}"
                    })
        return results
    
    def create_supplier_and_retry_action(self, supplier_name: str, original_action: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Creates a supplier in Odoo and then retries the original failed action.
        """
        try:
            logger.info(f"Attempting to create supplier '{supplier_name}' and retry action.")
            # Step 1: Create the supplier
            creation_result = self.odoo_service.create_supplier(supplier_name)
            
            if creation_result.get("status") in ["success", "skipped"]:
                logger.info(f"Supplier '{supplier_name}' created or already exists. Retrying original action.")
                # Step 2: Retry the original action by calling execute_plan with just that action
                retry_results = self.execute_plan([original_action])
                if retry_results and retry_results[0].get("status") == "success":
                    retry_results[0]['supplier_created'] = supplier_name
                
                return retry_results
            else:
                # The supplier creation itself failed
                error_message = creation_result.get("message", f"Failed to create supplier '{supplier_name}'.")
                return [{"status": "error", "message": error_message}]

        except Exception as e:
            logger.error(f"Error during create-and-retry for supplier '{supplier_name}': {e}", exc_info=True)
            return [{"status": "error", "message": f"A failure occurred while creating supplier '{supplier_name}': {str(e)}"}]
        
    # services/planning_service.py - Add these methods to your existing PlanningService class

    def reschedule_order(self, planned_order_id: str, new_due_date: str, reschedule_type: str) -> dict:
        """
        Reschedule a specific order to a new due date
        
        Args:
            planned_order_id: The ID of the planned order to reschedule
            new_due_date: New due date in YYYY-MM-DD format
            reschedule_type: 'prepone' or 'postpone'
        
        Returns:
            Dictionary with reschedule result
        """
        try:
            # Load current data
            df = self.data_service.load_data()
            
            # Find the order
            order_mask = df['planned_order_id'] == planned_order_id
            if not order_mask.any():
                raise PlanningError(f"Order {planned_order_id} not found")
            
            order_row = df[order_mask].iloc[0]
            current_date = pd.to_datetime(order_row['suggested_due_date']).date()
            new_date = datetime.strptime(new_due_date, '%Y-%m-%d').date()
            
            # Validate the reschedule operation
            if new_date < date.today():
                raise PlanningError("Cannot reschedule to a past date")
            
            if reschedule_type.lower() == 'prepone' and new_date > current_date:
                raise PlanningError("Cannot prepone to a later date")
            
            if reschedule_type.lower() == 'postpone' and new_date < current_date:
                raise PlanningError("Cannot postpone to an earlier date")
            
            # Create the reschedule action
            action = {
                'type': 'reschedule',
                'planned_order_id': planned_order_id,
                'item_name': order_row['item_name'],
                'item_type': order_row['item_type'],
                'current_due_date': str(current_date),
                'new_due_date': new_due_date,
                'reschedule_type': reschedule_type,
                'quantity': order_row['quantity'],
                'days_changed': (new_date - current_date).days
            }
            
            # If there's an existing order in Odoo, include update action
            existing_order = self._check_existing_order_in_odoo(planned_order_id)
            if existing_order:
                action['odoo_update_required'] = True
                action['existing_odoo_id'] = existing_order.get('id')
            
            return {
                'status': 'success',
                'action': action,
                'message': f"Order {planned_order_id} scheduled for {reschedule_type} from {current_date} to {new_date}"
            }
            
        except Exception as e:
            raise PlanningError(f"Failed to create reschedule action: {str(e)}")

    def create_bulk_reschedule_plan(self, reschedule_requests: List[dict]) -> List[dict]:
        """
        Create a plan for bulk rescheduling operations
        
        Args:
            reschedule_requests: List of dictionaries with reschedule requests
            Each dict should contain: planned_order_id, new_due_date, reschedule_type
        
        Returns:
            List of action results
        """
        try:
            actions = []
            
            for request in reschedule_requests:
                try:
                    result = self.reschedule_order(
                        planned_order_id=request['planned_order_id'],
                        new_due_date=request['new_due_date'],
                        reschedule_type=request['reschedule_type']
                    )
                    actions.append(result['action'])
                    
                except Exception as e:
                    # Add failed action with error details
                    actions.append({
                        'type': 'reschedule',
                        'planned_order_id': request['planned_order_id'],
                        'status': 'failed',
                        'error': str(e),
                        'reschedule_type': request['reschedule_type']
                    })
            
            return actions
            
        except Exception as e:
            raise PlanningError(f"Failed to create bulk reschedule plan: {str(e)}")

    def _check_existing_order_in_odoo(self, planned_order_id: str) -> Optional[dict]:
        """
        Check if an order already exists in Odoo for the given planned order ID
        """
        try:
            domain = [[self.ODOO_CUSTOM_FIELD_NAME, '=', planned_order_id]]
            # Check production orders
            production_orders = self.odoo_service.get_production_orders(domain=domain)
            if production_orders:
                production_orders[0]['item_type'] = 'Manufacture'
                return production_orders[0]
            
            purchase_orders = self.odoo_service.get_purchase_orders(domain=domain)
            if purchase_orders:
                purchase_orders[0]['item_type'] = 'Purchase'
                return purchase_orders[0]
            
            return None
        except Exception as e:
            logger.warning(f"Could not check existing order in Odoo: {str(e)}")
            return None

    def execute_reschedule_actions(self, reschedule_actions: List[dict]) -> List[dict]:
        """
        Execute reschedule actions in Odoo
        
        Args:
            reschedule_actions: List of reschedule action dictionaries
        
        Returns:
            List of execution results
        """
        try:
            results = []
            
            for action in reschedule_actions:
                planned_order_id = action.get('planned_order_id')
                new_due_date = action.get('new_due_date')
                try:
                    if not planned_order_id or not new_due_date:
                        raise PlanningError("Action is missing 'planned_order_id' or 'new_due_date'.")

                    # The execution step performs its own check, which is more robust.
                    existing_order = self._check_existing_order_in_odoo(planned_order_id)

                    if existing_order:
                        # If it exists, UPDATE it
                        odoo_result = self._update_existing_order_date(
                            order_id=existing_order['id'],
                            new_date=new_due_date,
                            item_type=existing_order['item_type']
                        )
                        results.append({
                            'planned_order_id': planned_order_id,
                            'status': 'success',
                            'message': f"Updated existing Odoo order {existing_order.get('name', '')} to new date {new_due_date}",
                            'odoo_result': odoo_result
                        })
                    else:
                        # If it does NOT exist, report it and do nothing in Odoo
                        results.append({
                            'planned_order_id': planned_order_id,
                            'status': 'success',
                            'message': f"Updated planned order due date to {new_due_date}",
                            'note': 'Order not yet created in Odoo'
                        })

                    # Always update the local data file to maintain consistency
                    self._update_local_order_date(planned_order_id, new_due_date)

                except Exception as e:
                    logger.error(f"Failed to execute reschedule for {planned_order_id}: {e}", exc_info=True)
                    results.append({
                        'planned_order_id': planned_order_id,
                        'status': 'failed',
                        'message': f"Failed to execute reschedule: {str(e)}"
                    })
            return results

            
        except Exception as e:
            raise PlanningError(f"Failed to execute reschedule actions: {str(e)}")

    def _update_existing_order_date(self, order_id: int, new_date: str, item_type: str) -> dict:
        """
        Update the due date of an existing order in Odoo
        """
        try:
            item_type_lower = item_type.lower()
            
            print(f"DEBUG: Attempting to update Odoo order ID: {order_id}, Type: '{item_type_lower}', New Date: {new_date}")

            if item_type_lower == 'manufacture':
                # The date field for manufacturing orders is 'date_planned_start'
                values_to_update = {'date_start': new_date}
                print(f"DEBUG: Calling update_production_order with values: {values_to_update}")
                result = self.odoo_service.update_production_order(
                    order_id=order_id,
                    values=values_to_update
                )
            elif item_type_lower == 'purchase':
                # The date field for purchase orders is 'date_planned'
                values_to_update = {'date_planned': new_date}
                print(f"DEBUG: Calling update_purchase_order with values: {values_to_update}")
                result = self.odoo_service.update_purchase_order(
                    order_id=order_id,
                    values=values_to_update
                )
            else:
                # This case should not be reached if the check is working
                raise PlanningError(f"Unknown item_type '{item_type}' for Odoo update.")
            
            print(f"DEBUG: Odoo API response for update: {result}")
            return result
            
        except Exception as e:
            raise PlanningError(f"Failed to update existing order in Odoo: {str(e)}")

    def _update_local_order_date(self, planned_order_id: str, new_due_date: str):
        """
        Update the due date in local data storage
        """
        try:
            # This is where you'd update your CSV file or database
            # Implementation depends on your data storage mechanism
            
            df = self.data_service.load_data()
            mask = df['planned_order_id'] == planned_order_id
            
            if mask.any():
                df.loc[mask, 'suggested_due_date'] = new_due_date
                # Save back to storage
                self.data_service.save_data(df)
                logger.info(f"Updated local data for order {planned_order_id} to {new_due_date}")
            else:
                logger.warning(f"Order {planned_order_id} not found in local data for update")
                
        except Exception as e:
            logger.error(f"Failed to update local data: {str(e)}")
            # Don't raise exception here as this might be non-critical

    def _overwrite_supplier_from_rankings(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Looks up the top-ranked supplier for 'Purchase' items using the DataService
        and overwrites the supplier in the DataFrame. Falls back gracefully.
        """
        try:
            # 1. Get supplier rankings from the dedicated service method
            df_rankings = self.data_service.load_supplier_rankings()

            # 2. Graceful fallback if the ranking data is empty (file not found, corrupt, etc.)
            if df_rankings.empty:
                logger.warning("Supplier ranking data is not available. Proceeding with default suppliers.")
                return orders_df

            # 3. Find the top-ranked supplier (where rank is 1)
            top_supplier_series = df_rankings[df_rankings['rank'] == 1]

            if top_supplier_series.empty:
                logger.warning("No supplier with rank 1 was found in the ranking data. Using default suppliers.")
                return orders_df

            # 4. Get the name of the top supplier. The ranking file has 'supplier_name'.
            top_supplier_name = top_supplier_series.iloc[0]['supplier_name']
            logger.info(f"Identified '{top_supplier_name}' as the top-ranked supplier.")

            # 5. Create a copy to avoid pandas' SettingWithCopyWarning
            modified_orders_df = orders_df.copy()

            # 6. Identify which rows to update (only 'Purchase' items)
            purchase_mask = modified_orders_df['item_type'].str.lower() == 'purchase'
            
            if purchase_mask.any():
                # 7. Overwrite the supplier. The main data file uses 'supplier_name_for_odoo'.
                original_suppliers = modified_orders_df.loc[purchase_mask, 'supplier_name_for_odoo'].unique()
                modified_orders_df.loc[purchase_mask, 'supplier_name_for_odoo'] = top_supplier_name
                logger.info(f"Overwrote supplier for {purchase_mask.sum()} purchase orders. Original(s): {list(original_suppliers)}. New: '{top_supplier_name}'.")
            
            return modified_orders_df

        except Exception as e:
            # Catch any other unexpected errors during the logic
            logger.error(f"An unexpected error occurred while overwriting suppliers: {e}. Proceeding with default suppliers.")
            return orders_df