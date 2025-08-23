# config/settings.py
import os
from typing import Optional
from pydantic_settings import BaseSettings
import pandas as pd

class Settings(BaseSettings):
    # AI Configuration
    gemini_api_key: str

    # Odoo Configuration
    odoo_url: str
    odoo_db: str
    odoo_username: str
    odoo_password: str

    # Application Settings
    debug: bool = False
    log_level: str = "INFO"
    session_timeout: int = 3600  # 1 hour

    # Data Settings
    # Correctly resolve the path to the 'data' directory from the project root
    project_root: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir: str = os.path.join(project_root, "data")
    orders_file: str = "planned_orders.csv"
    suppliers_file: str = "suppliers.csv"

    # Pandas Display Settings
    max_display_rows: Optional[int] = None
    max_display_cols: Optional[int] = None
    display_width: int = 2000
    max_col_width: Optional[int] = None

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

# Global settings instance
settings = Settings()

# Configure pandas display options
pd.set_option('display.max_rows', settings.max_display_rows)
pd.set_option('display.max_columns', settings.max_display_cols)
pd.set_option('display.width', settings.display_width)
pd.set_option('display.max_colwidth', settings.max_col_width)