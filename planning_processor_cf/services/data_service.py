# services/data_service.py
import pandas as pd
import os
from typing import Optional
from config.settings import settings
from utils.exceptions import DataLoadError
import logging

logger = logging.getLogger(__name__)

class DataService:
    def __init__(self):
        self._df_cache: Optional[pd.DataFrame] = None

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