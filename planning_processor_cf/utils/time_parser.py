# utils/time_parser.py
import pandas as pd
import re
from datetime import datetime, timedelta, date
from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
from .exceptions import TimeParsingError

class TimeParser:
    def filter_dataframe_by_time(self, df: pd.DataFrame, time_description: str, date_column: str) -> pd.DataFrame:
        if date_column not in df.columns:
            raise TimeParsingError(f"Date column '{date_column}' not found in DataFrame")
        
        df = df.copy()
        df[date_column] = pd.to_datetime(df[date_column])
        time_desc_lower = time_description.lower()
        today = date.today()

        if "today" in time_desc_lower: return df[df[date_column].dt.date == today]
        if "tomorrow" in time_desc_lower: return df[df[date_column].dt.date == today + timedelta(days=1)]
        if "day after tomorrow" in time_desc_lower: return df[df[date_column].dt.date == today + timedelta(days=2)]
        
        if "this week" in time_desc_lower:
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return df[(df[date_column].dt.date >= start) & (df[date_column].dt.date <= end)]
        
        if "next week" in time_desc_lower:
            start = today + timedelta(days=(7 - today.weekday()))
            end = start + timedelta(days=6)
            return df[(df[date_column].dt.date >= start) & (df[date_column].dt.date <= end)]
        
        date_match = re.search(r'(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}-\d{4}|\d{1,2}/\d{1,2}/\d{4})', time_desc_lower)
        if date_match:
            target_date = parse_date(date_match.group(1), dayfirst=True).date()
            return df[df[date_column].dt.date == target_date]
        
        match = re.search(r'(\d+)\s*(day|week|month)', time_desc_lower, re.IGNORECASE)
        if match:
            value, unit = int(match.group(1)), match.group(2).lower()
            delta = timedelta(days=value) if 'day' in unit else timedelta(weeks=value) if 'week' in unit else relativedelta(months=value)
            end_date = datetime.now().date() + delta
            return df[(df[date_column].dt.date >= today) & (df[date_column].dt.date <= end_date)]
            
        raise TimeParsingError(f"Could not understand the time description: '{time_description}'")

    def parse_duration_to_days(self, duration_str: str) -> int:
        match = re.search(r'(\d+)\s*(day|week|month)', duration_str, re.IGNORECASE)
        if not match:
            raise TimeParsingError("Invalid duration format. Use 'X days/weeks/months'")
        value, unit = int(match.group(1)), match.group(2).lower()
        if 'day' in unit: return value
        if 'week' in unit: return value * 7
        if 'month' in unit: return value * 30
        return 0