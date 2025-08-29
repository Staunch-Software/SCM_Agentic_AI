# services/planning_service.py
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, date
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
            # Check production orders
            production_orders = self.odoo_service.get_production_orders(
                domain=[['x_planned_order_id', '=', planned_order_id]]
            )
            
            if production_orders:
                return production_orders[0]
            
            # Check purchase orders
            purchase_orders = self.odoo_service.get_purchase_orders(
                domain=[['x_planned_order_id', '=', planned_order_id]]
            )
            
            if purchase_orders:
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
                try:
                    if action.get('status') == 'failed':
                        results.append({
                            'planned_order_id': action['planned_order_id'],
                            'status': 'skipped',
                            'message': f"Skipped due to planning error: {action.get('error', 'Unknown error')}"
                        })
                        continue
                    
                    planned_order_id = action['planned_order_id']
                    new_due_date = action['new_due_date']
                    
                    # Update existing order in Odoo if it exists
                    if action.get('odoo_update_required') and action.get('existing_odoo_id'):
                        odoo_result = self._update_existing_order_date(
                            order_id=action['existing_odoo_id'],
                            new_date=new_due_date,
                            item_type=action['item_type']
                        )
                        
                        results.append({
                            'planned_order_id': planned_order_id,
                            'status': 'success',
                            'message': f"Updated existing Odoo order to new date {new_due_date}",
                            'odoo_result': odoo_result
                        })
                    
                    else:
                        # For orders not yet in Odoo, just update local data
                        # This would typically update your local CSV or database
                        self._update_local_order_date(planned_order_id, new_due_date)
                        
                        results.append({
                            'planned_order_id': planned_order_id,
                            'status': 'success',
                            'message': f"Updated planned order due date to {new_due_date}",
                            'note': 'Order not yet created in Odoo'
                        })
                    
                except Exception as e:
                    results.append({
                        'planned_order_id': action.get('planned_order_id', 'unknown'),
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
            if item_type.lower() == 'make':
                # Update production order
                result = self.odoo_service.update_production_order(
                    order_id=order_id,
                    values={'date_planned_start': new_date}
                )
            else:
                # Update purchase order
                result = self.odoo_service.update_purchase_order(
                    order_id=order_id,
                    values={'date_planned': new_date}
                )
            
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