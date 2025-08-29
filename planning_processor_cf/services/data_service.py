# services/data_service.py
import pandas as pd
import os
import re
from typing import Optional
from config.settings import settings
from utils.exceptions import DataLoadError
import logging

logger = logging.getLogger(__name__)

class DataService:
    def __init__(self):
        self._df_cache: Optional[pd.DataFrame] = None

    def _clean_column_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardizes column headers to lowercase_with_underscores."""
        cols = df.columns
        new_cols = [col.strip().replace(' ', '_').lower() for col in cols]
        df.columns = new_cols
        return df

    def _extract_item_id(self, item_string: str) -> Optional[str]:
        """Extracts an item ID like '[COMP0004]' from a string."""
        if not isinstance(item_string, str):
            return None
        match = re.search(r'\[(.*?)\]', item_string)
        return match.group(1) if match else None

    def load_data(self, force_reload: bool = False) -> pd.DataFrame:
        """
        Loads and robustly cleans the planned orders data from the CSV file.
        """
        if self._df_cache is not None and not force_reload:
            return self._df_cache.copy()
        try:
            orders_path = os.path.join(settings.data_dir, settings.orders_file)
            if not os.path.exists(orders_path):
                raise DataLoadError(f"Orders file not found: {orders_path}")

            df = pd.read_csv(orders_path)

            # Step 1: Standardize column headers
            df = self._clean_column_headers(df)
            logger.info(f"Cleaned column headers: {list(df.columns)}")

            # --- THIS IS THE FIX ---
            # Step 2: Specifically look for 'planned_id' and rename it to the application's standard 'planned_order_id'
            if 'planned_id' in df.columns:
                df.rename(columns={'planned_id': 'planned_order_id'}, inplace=True)
            # --- END OF FIX ---

            # Step 3: Ensure all required columns exist, adding them if they don't
            required_cols = {
                'planned_order_id': None, 'item': None, 'item_id': None,
                'quantity': 0, 'suggested_due_date': None, 'item_type': None,
                'supplier': None, 'reschedule_out_days': 0
            }
            for col, default in required_cols.items():
                if col not in df.columns:
                    df[col] = default
                    logger.warning(f"Column '{col}' was missing. Added it with default values.")

            # Step 4: Extract item_id from the 'item' column
            df['item_id'] = df['item'].apply(self._extract_item_id)
            
            # Step 5: Process the date column
            if 'suggested_due_date' not in df.columns:
                raise DataLoadError("Fatal: Column 'suggested_due_date' not found after cleaning.")
            df['suggested_due_date'] = pd.to_datetime(df['suggested_due_date'], dayfirst=True)

            # Step 6: Rename supplier column for Odoo service compatibility
            if 'supplier' in df.columns:
                df.rename(columns={'supplier': 'supplier_name_for_odoo'}, inplace=True)

            self._df_cache = df
            logger.info(f"Successfully loaded and cleaned {len(self._df_cache)} records from planning data.")
            return self._df_cache.copy()
            
        except Exception as e:
            logger.error(f"Failed to load data: {e}", exc_info=True)
            raise DataLoadError(f"Failed to load data: {str(e)}")