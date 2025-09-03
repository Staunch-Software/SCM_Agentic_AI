# tools/rescheduling_tool.py
from typing import Optional, List, Dict, Any
import pandas as pd
from datetime import datetime, date, timedelta
from .base_tool import BaseTool
from services.data_service import DataService
from services.planning_service import PlanningService
from utils.time_parser import TimeParser
import json
import logging

logger = logging.getLogger(__name__)

class ReschedulingTool(BaseTool):
    def __init__(self, data_service: DataService, planning_service: PlanningService, session_manager):
        super().__init__(session_manager)
        self.data_service = data_service
        self.planning_service = planning_service
        self.time_parser = TimeParser()

    def analyze_rescheduling_eligibility(self, session_id: str, planned_order_ids: Optional[List[str]] = None) -> str:
        """
        Analyze which orders are eligible for prepone vs postpone based on current date
        """
        self.log_tool_execution("analyze_rescheduling_eligibility", session_id, planned_order_ids=planned_order_ids)
        
        try:
            df = self.data_service.load_data()
            
            # Filter by specific IDs if provided
            if planned_order_ids:
                df = df[df['planned_order_id'].isin(planned_order_ids)]
                
            if df.empty:
                return self.format_error_response("No orders found matching the criteria")
            
            current_date = date.today()
            
            # Prepare table data
            table_data = []
            detailed_analysis = []
            
            current_date = date.today()
            for _, row in df.iterrows():
                order_id = row['planned_order_id']
                try:
                    # Ensure both are date objects for proper comparison
                    suggested_date = pd.to_datetime(row['suggested_due_date']).date()
                    days_difference = (suggested_date - current_date).days
                    
                    # Debug logging - remove after fixing
                    print(f"DEBUG: Order {order_id}, Suggested: {suggested_date}, Current: {current_date}, Diff: {days_difference}")
                    
                except Exception as e:
                    print(f"ERROR in date calculation for {order_id}: {e}")
                    days_difference = 0  # Fallback
                
                # Determine eligibility status for table
                if days_difference <= 0:
                    eligibility_status = "Postpone Only (Overdue)"
                elif days_difference == 1:
                    eligibility_status = "Postpone Only (Due Tomorrow)"
                else:
                    eligibility_status = "Prepone/Postpone"
                
                # Add to table data
                table_data.append([
                    order_id,
                    row['item'],
                    str(suggested_date),
                    days_difference,
                    eligibility_status
                ])
                
                # Keep detailed analysis for summary
                analysis = {
                    'planned_order_id': order_id,
                    'item': row['item'],
                    'current_date': str(current_date),
                    'suggested_due_date': str(suggested_date),
                    'days_from_today': days_difference,
                    'can_prepone': days_difference > 1,
                    'can_postpone': True,
                    'max_prepone_days': max(0, days_difference - 1) if days_difference > 1 else 0
                }
                
                if days_difference <= 0:
                    analysis['status'] = 'overdue_or_today'
                    analysis['recommendation'] = 'Can only postpone - order is due today or overdue'
                elif days_difference == 1:
                    analysis['status'] = 'tomorrow'
                    analysis['recommendation'] = 'Can only postpone - order is due tomorrow'
                else:
                    analysis['status'] = 'future'
                    analysis['recommendation'] = f'Can prepone up to {analysis["max_prepone_days"]} days or postpone any number of days'
                
                detailed_analysis.append(analysis)
            
            # Convert table_data to the expected format with headers and rows
            headers = ["Order ID", "Item Name", "Due Date", "Days From Today", "Rescheduling Options"]
            rows = []

            for row_data in table_data:
                row_dict = {
                    "Order ID": row_data[0],
                    "Item Name": row_data[1], 
                    "Due Date": row_data[2],
                    "Days From Today": str(row_data[3]),
                    "Rescheduling Options": row_data[4]
                }
                rows.append(row_dict)

            table_response = {
                "display_type": "table",
                "headers": headers,
                "rows": rows,
                "analysis": detailed_analysis,  # Add this!
                "summary": {
                    "total_orders": len(detailed_analysis),
                    "can_prepone": len([a for a in detailed_analysis if a['can_prepone']]),
                    "postpone_only": len([a for a in detailed_analysis if not a['can_prepone']])
                }
            }
            
            return json.dumps(table_response)
            
        except Exception as e:
            return self.format_error_response(f"Failed to analyze rescheduling eligibility: {str(e)}")

    def create_rescheduling_plan(self, session_id: str, planned_order_ids: List[str], 
                               reschedule_type: str, target_date: Optional[str] = None, 
                               days_offset: Optional[int] = None, 
                               individual_dates: bool = False) -> str:
        """
        Create a rescheduling plan for multiple orders
        
        Args:
            session_id: Session identifier
            planned_order_ids: List of order IDs to reschedule
            reschedule_type: 'prepone' or 'postpone'
            target_date: Specific target date (YYYY-MM-DD format)
            days_offset: Number of days to offset from current suggested date
            individual_dates: Whether to ask for individual dates for each order
        """
        self.log_tool_execution("create_rescheduling_plan", session_id, 
                               planned_order_ids=planned_order_ids, 
                               reschedule_type=reschedule_type,
                               target_date=target_date,
                               days_offset=days_offset,
                               individual_dates=individual_dates)
        
        try:
            # First analyze eligibility
            eligibility_result = json.loads(self.analyze_rescheduling_eligibility(session_id, planned_order_ids))
            
            if "error" in eligibility_result:
                return self.format_error_response(eligibility_result["error"])
            
            analysis = eligibility_result["analysis"]
            current_date = date.today()
            
            # Validate rescheduling requests against eligibility
            invalid_orders = []
            valid_orders = []
            
            for order_analysis in analysis:
                order_id = order_analysis['planned_order_id']
                
                if reschedule_type.lower() == 'prepone' and not order_analysis['can_prepone']:
                    invalid_orders.append({
                        'order_id': order_id,
                        'reason': f"Cannot prepone - order is due in {order_analysis['days_from_today']} day(s)"
                    })
                else:
                    # Calculate new date
                    current_suggested_date = datetime.strptime(order_analysis['suggested_due_date'], '%Y-%m-%d').date()
                    
                    if target_date:
                        new_date = datetime.strptime(target_date, '%Y-%m-%d').date()
                        # Validate target date is not in the past
                        if new_date < current_date:
                            invalid_orders.append({
                                'order_id': order_id,
                                'reason': f"Target date {target_date} is in the past"
                            })
                            continue
                    elif days_offset:
                        if reschedule_type.lower() == 'prepone':
                            new_date = current_suggested_date - timedelta(days=abs(days_offset))
                            # Validate prepone doesn't go to past
                            if new_date < current_date:
                                invalid_orders.append({
                                    'order_id': order_id,
                                    'reason': f"Cannot prepone by {days_offset} days - would result in past date"
                                })
                                continue
                        else:  # postpone
                            new_date = current_suggested_date + timedelta(days=abs(days_offset))
                    else:
                        invalid_orders.append({
                            'order_id': order_id,
                            'reason': "No target date or days offset specified"
                        })
                        continue
                    
                    valid_orders.append({
                        'planned_order_id': order_id,
                        'item': order_analysis['item'],
                        'current_suggested_date': order_analysis['suggested_due_date'],
                        'new_due_date': str(new_date),
                        'reschedule_type': reschedule_type,
                        'days_changed': (new_date - current_suggested_date).days
                    })
            
            # Store the rescheduling plan in session
            rescheduling_plan = {
                'valid_orders': valid_orders,
                'invalid_orders': invalid_orders,
                'reschedule_type': reschedule_type,
                'created_at': datetime.now().isoformat()
            }
            
            self.session_manager.update_session(session_id, last_action_plan=rescheduling_plan)
            
            return json.dumps({
                'plan_created': True,
                'valid_orders_count': len(valid_orders),
                'invalid_orders_count': len(invalid_orders),
                'valid_orders': valid_orders,
                'invalid_orders': invalid_orders,
                'requires_confirmation': True
            })
            
        except Exception as e:
            return self.format_error_response(f"Failed to create rescheduling plan: {str(e)}")

    # def execute_rescheduling_plan(self, session_id: str) -> str:
    #     """
    #     Execute the rescheduling plan stored in session
    #     """
    #     self.log_tool_execution("execute_rescheduling_plan", session_id)
        
    #     try:
    #         session_data = self.session_manager.get_session(session_id)
    #         plan_to_execute = session_data.last_action_plan

    #         if not plan_to_execute:
    #             return self.format_error_response("No rescheduling plan found. Please create a plan first.")

    #         valid_orders = plan_to_execute.get('valid_orders', [])

    #         if not valid_orders:
    #             return self.format_error_response("No valid orders to reschedule in the current plan")
            
    #         # Execute rescheduling through planning service
    #         results = []
    #         for order in valid_orders:
    #             pass
    #         # Clear the rescheduling plan from session
    #         self.session_manager.update_session(session_id, rescheduling_plan=None)
            
    #         success_count = len([r for r in results if r['status'] == 'success'])
            
    #         return json.dumps({
    #             'execution_complete': True,
    #             'total_orders': len(results),
    #             'successful': success_count,
    #             'failed': len(results) - success_count,
    #             'results': results
    #         })
            
    #     except Exception as e:
    #         return self.format_error_response(f"Failed to execute rescheduling plan: {str(e)}")

    def get_rescheduling_options(self, session_id: str, planned_order_id: Optional[str] = None) -> str:
        """
        Get available rescheduling options for orders
        """
        self.log_tool_execution("get_rescheduling_options", session_id, planned_order_id=planned_order_id)
        
        try:
            if planned_order_id:
                # Get options for specific order
                eligibility = json.loads(self.analyze_rescheduling_eligibility(session_id, [planned_order_id]))
            else:
                # Get available orders that can be rescheduled
                df = self.data_service.load_data()
                order_ids = df['planned_order_id'].tolist()[:10]  # Limit to first 10 for display
                eligibility = json.loads(self.analyze_rescheduling_eligibility(session_id, order_ids))
            
            if "error" in eligibility:
                return self.format_error_response(eligibility["error"])
            
            return json.dumps({
                'available_orders': eligibility["analysis"],
                'summary': eligibility["summary"],
                'options': {
                    'can_specify_target_date': True,
                    'can_specify_days_offset': True,
                    'can_reschedule_multiple': True,
                    'can_set_individual_dates': True
                }
            })
            
        except Exception as e:
            return self.format_error_response(f"Failed to get rescheduling options: {str(e)}")

    def validate_rescheduling_request(self, session_id: str, planned_order_ids: List[str], 
                                reschedule_type: str, target_date: Optional[str] = None, 
                                days_offset: Optional[int] = None) -> str:
        """
        Validate a rescheduling request before creating the plan
        """
        self.log_tool_execution("validate_rescheduling_request", session_id,
                            planned_order_ids=planned_order_ids,
                            reschedule_type=reschedule_type,
                            target_date=target_date,
                            days_offset=days_offset)
        
        try:
            # Debug logging
            logger.info(f"Validation inputs - session_id: {session_id}, order_ids: {planned_order_ids}, "
                    f"type: {reschedule_type}, target_date: {target_date}, days_offset: {days_offset}")
            
            # Validate inputs first
            if not planned_order_ids:
                return self.format_error_response("No order IDs provided for validation")
            
            if not reschedule_type:
                return self.format_error_response("No reschedule type specified")
            
            # Get eligibility analysis
            try:
                eligibility_result = json.loads(self.analyze_rescheduling_eligibility(session_id, planned_order_ids))
                logger.info(f"Eligibility result structure: {eligibility_result.keys()}")
            except Exception as e:
                logger.error(f"Failed to analyze eligibility: {str(e)}")
                return self.format_error_response(f"Failed to analyze order eligibility: {str(e)}")
            
            if "error" in eligibility_result:
                return self.format_error_response(eligibility_result["error"])
            
            # Check if we have the expected data structure
            if "analysis" not in eligibility_result:
                logger.error(f"Missing 'analysis' key in eligibility result: {eligibility_result}")
                return self.format_error_response("Invalid eligibility analysis format")
            
            analysis = eligibility_result["analysis"]
            validation_results = []
            current_date = date.today()
            
            for order_analysis in analysis:
                order_id = order_analysis['planned_order_id']
                validation = {
                    'planned_order_id': order_id,
                    'is_valid': True,
                    'warnings': [],
                    'errors': []
                }
                
                # Check if reschedule type is valid for this order
                if reschedule_type.lower() == 'prepone' and not order_analysis['can_prepone']:
                    validation['is_valid'] = False
                    validation['errors'].append(f"Cannot prepone - order is due in {order_analysis['days_from_today']} day(s)")
                
                # Validate target date if provided
                if target_date:
                    try:
                        target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
                        if target_date_obj < current_date:
                            validation['is_valid'] = False
                            validation['errors'].append("Target date cannot be in the past")
                        
                        current_suggested = datetime.strptime(order_analysis['suggested_due_date'], '%Y-%m-%d').date()
                        days_diff = (target_date_obj - current_suggested).days
                        
                        if reschedule_type.lower() == 'prepone' and days_diff > 0:
                            validation['warnings'].append("Target date is later than current date - this is postponing, not preponing")
                        elif reschedule_type.lower() == 'postpone' and days_diff < 0:
                            validation['warnings'].append("Target date is earlier than current date - this is preponing, not postponing")
                            
                    except ValueError:
                        validation['is_valid'] = False
                        validation['errors'].append("Invalid target date format. Use YYYY-MM-DD")
                
                # Validate days offset if provided
                if days_offset:
                    try:
                        days_offset_int = int(days_offset)
                        current_suggested = datetime.strptime(order_analysis['suggested_due_date'], '%Y-%m-%d').date()
                        
                        if reschedule_type.lower() == 'prepone':
                            new_date = current_suggested - timedelta(days=abs(days_offset_int))
                            if new_date < current_date:
                                validation['is_valid'] = False
                                validation['errors'].append(f"Preponing by {days_offset_int} days would result in a past date")
                    except (ValueError, TypeError):
                        validation['is_valid'] = False
                        validation['errors'].append("Invalid days offset - must be a number")
                
                validation_results.append(validation)
            
            overall_valid = all(v['is_valid'] for v in validation_results)
            
            return json.dumps({
                'overall_valid': overall_valid,
                'validations': validation_results,
                'can_proceed': overall_valid
            })
            
        except Exception as e:
            logger.error(f"Validation failed with exception: {str(e)}")
            return self.format_error_response(f"Failed to validate rescheduling request: {str(e)}")