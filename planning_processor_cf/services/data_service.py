# services/data_service.py
import pandas as pd
import os
from typing import Optional, Dict,List, Any
from datetime import datetime, timedelta, date
from config.settings import settings
from utils.exceptions import DataLoadError
import logging

logger = logging.getLogger(__name__)

class DataService:
    def __init__(self):
        self._df_cache: Optional[pd.DataFrame] = None
        self.data_path = os.path.join(settings.data_dir, settings.orders_file)

    def load_data(self, force_reload: bool = False) -> pd.DataFrame:
        if self._df_cache is not None and not force_reload:
            return self._df_cache.copy()
        try:
            orders_path = os.path.join(settings.data_dir, settings.orders_file)
            suppliers_path = os.path.join(settings.data_dir, settings.suppliers_file)

            if not os.path.exists(orders_path):
                raise DataLoadError(f"Orders file not found: {orders_path}")
            if not os.path.exists(suppliers_path):
                raise DataLoadError(f"Suppliers file not found: {suppliers_path}")

            df_orders = pd.read_csv(orders_path)
            df_suppliers = pd.read_csv(suppliers_path)

            df_orders['suggested_due_date'] = pd.to_datetime(df_orders['suggested_due_date'])
            df_suppliers.rename(columns={'supplier_name': 'supplier_name_for_odoo'}, inplace=True)

            self._df_cache = pd.merge(df_orders, df_suppliers, on='supplier_id', how='left')
            logger.info(f"Loaded {len(self._df_cache)} records from planning data")
            return self._df_cache.copy()
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            raise DataLoadError(f"Failed to load data: {str(e)}")
    
    def save_data(self, df: pd.DataFrame) -> bool:
        """
        Save DataFrame back to the data source (CSV file)
    
        Args:
            df: DataFrame to save
      
        Returns:
            Boolean indicating success
        """
        try:
            # Assuming you're using CSV - adjust path as needed
            df.to_csv(self.data_path, index=False)
            logger.info(f"Successfully saved data to {self.data_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save data: {str(e)}")
            return False

    def update_order_due_date(self, planned_order_id: str, new_due_date: str) -> bool:
        """
        Update the due date for a specific order in the data
        
        Args:
            planned_order_id: The order ID to update
            new_due_date: New due date in YYYY-MM-DD format
            
        Returns:
            Boolean indicating success
        """
        try:
            df = self.load_data()
            
            # Find the order
            mask = df['planned_order_id'] == planned_order_id
            
            if not mask.any():
                logger.warning(f"Order {planned_order_id} not found in data")
                return False
            
            # Update the due date
            df.loc[mask, 'suggested_due_date'] = new_due_date
            
            # Recalculate reschedule_out_days if that column exists
            if 'reschedule_out_days' in df.columns:
                current_date = date.today()
                new_date = datetime.strptime(new_due_date, '%Y-%m-%d').date()
                reschedule_days = max(0, (current_date - new_date).days)
                df.loc[mask, 'reschedule_out_days'] = reschedule_days
            
            # Save the updated data
            success = self.save_data(df)
            
            if success:
                logger.info(f"Updated due date for order {planned_order_id} to {new_due_date}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to update order due date: {str(e)}")
            return False

    def bulk_update_due_dates(self, updates: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Update multiple orders' due dates in bulk
        
        Args:
            updates: List of dictionaries with 'planned_order_id' and 'new_due_date'
            
        Returns:
            Dictionary with success/failure counts and details
        """
        try:
            df = self.load_data()
            
            successful_updates = []
            failed_updates = []
            
            current_date = date.today()
            
            for update in updates:
                planned_order_id = update['planned_order_id']
                new_due_date = update['new_due_date']
                
                try:
                    # Find the order
                    mask = df['planned_order_id'] == planned_order_id
                    
                    if not mask.any():
                        failed_updates.append({
                            'planned_order_id': planned_order_id,
                            'error': 'Order not found'
                        })
                        continue
                    
                    # Update the due date
                    df.loc[mask, 'suggested_due_date'] = new_due_date
                    
                    # Recalculate reschedule_out_days if that column exists
                    if 'reschedule_out_days' in df.columns:
                        new_date = datetime.strptime(new_due_date, '%Y-%m-%d').date()
                        reschedule_days = max(0, (current_date - new_date).days)
                        df.loc[mask, 'reschedule_out_days'] = reschedule_days
                    
                    successful_updates.append({
                        'planned_order_id': planned_order_id,
                        'new_due_date': new_due_date
                    })
                    
                except Exception as e:
                    failed_updates.append({
                        'planned_order_id': planned_order_id,
                        'error': str(e)
                    })
            
            # Save all updates at once
            if successful_updates:
                save_success = self.save_data(df)
                if not save_success:
                    # If save fails, mark all as failed
                    failed_updates.extend(successful_updates)
                    successful_updates = []
            
            result = {
                'total_requested': len(updates),
                'successful': len(successful_updates),
                'failed': len(failed_updates),
                'successful_updates': successful_updates,
                'failed_updates': failed_updates
            }
            
            logger.info(f"Bulk update completed: {result['successful']}/{result['total_requested']} successful")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed bulk update operation: {str(e)}")
            return {
                'total_requested': len(updates),
                'successful': 0,
                'failed': len(updates),
                'error': str(e)
            }

    def get_orders_by_date_range(self, start_date: str, end_date: str, 
                            date_column: str = 'suggested_due_date') -> pd.DataFrame:
        """
        Get orders within a specific date range
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            date_column: Column name to filter by
            
        Returns:
            Filtered DataFrame
        """
        try:
            df = self.load_data()
            
            if date_column not in df.columns:
                raise ValueError(f"Date column '{date_column}' not found")
            
            # Convert to datetime for comparison
            df[date_column] = pd.to_datetime(df[date_column])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            # Filter by date range
            filtered_df = df[
                (df[date_column] >= start_dt) & 
                (df[date_column] <= end_dt)
            ]
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"Failed to filter by date range: {str(e)}")
            return pd.DataFrame()

    def get_reschedulable_orders(self, min_days_ahead: int = 1) -> pd.DataFrame:
        """
        Get orders that are eligible for rescheduling
        
        Args:
            min_days_ahead: Minimum days ahead to be eligible for preponing
            
        Returns:
            DataFrame with rescheduling eligibility info
        """
        try:
            df = self.load_data()
            
            if 'suggested_due_date' not in df.columns:
                raise ValueError("suggested_due_date column not found")
            
            current_date = date.today()
            df['suggested_due_date'] = pd.to_datetime(df['suggested_due_date'])
            
            # Calculate days from today
            df['days_from_today'] = (df['suggested_due_date'].dt.date - current_date).dt.days
            
            # Add eligibility flags
            df['can_prepone'] = df['days_from_today'] > min_days_ahead
            df['can_postpone'] = True  # Can always postpone
            df['max_prepone_days'] = df.apply(
                lambda x: max(0, x['days_from_today'] - 1) if x['can_prepone'] else 0, 
                axis=1
            )
            
            # Add status
            def get_status(days):
                if days <= 0:
                    return 'overdue_or_today'
                elif days == 1:
                    return 'tomorrow'
                else:
                    return 'future'
            
            df['reschedule_status'] = df['days_from_today'].apply(get_status)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to get reschedulable orders: {str(e)}")
            return pd.DataFrame()

    def backup_data(self, backup_suffix: str = None) -> str:
        """
        Create a backup of the current data
        
        Args:
            backup_suffix: Optional suffix for backup filename
            
        Returns:
            Path to backup file
        """
        try:
            df = self.load_data()
            
            if backup_suffix is None:
                backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            backup_path = f"{self.data_path}.backup_{backup_suffix}"
            df.to_csv(backup_path, index=False)
            
            logger.info(f"Data backed up to {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Failed to backup data: {str(e)}")
            return ""

    def validate_data_integrity(self) -> Dict[str, Any]:
        """
        Validate the integrity of the data after updates
        
        Returns:
            Dictionary with validation results
        """
        try:
            df = self.load_data()
            
            validation_results = {
                'total_records': len(df),
                'issues': [],
                'warnings': []
            }
            
            # Check for required columns
            required_columns = ['planned_order_id', 'suggested_due_date', 'item_type']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                validation_results['issues'].append(f"Missing required columns: {missing_columns}")
            
            # Check for duplicate planned_order_ids
            duplicates = df['planned_order_id'].duplicated().sum()
            if duplicates > 0:
                validation_results['issues'].append(f"Found {duplicates} duplicate planned_order_ids")
            
            # Check for invalid dates
            try:
                pd.to_datetime(df['suggested_due_date'])
            except:
                validation_results['issues'].append("Invalid dates found in suggested_due_date column")
            
            # Check for past dates
            current_date = date.today()
            past_dates = pd.to_datetime(df['suggested_due_date']).dt.date < current_date
            past_count = past_dates.sum()
            
            if past_count > 0:
                validation_results['warnings'].append(f"{past_count} orders have past due dates")
            
            validation_results['is_valid'] = len(validation_results['issues']) == 0
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Failed to validate data integrity: {str(e)}")
            return {
                'is_valid': False,
                'issues': [f"Validation failed: {str(e)}"]
            }