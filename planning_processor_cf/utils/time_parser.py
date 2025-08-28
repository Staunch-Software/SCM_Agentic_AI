# utils/time_parser.py
import pandas as pd
import re
from datetime import datetime, timedelta, date
from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
from typing import Tuple, Optional, Dict, Any, List
from .exceptions import TimeParsingError
import calendar

class TimeParser:
    def __init__(self):
        self.today = date.today()
        self.now = datetime.now()
        self._init_patterns()
        self._init_business_dates()

    def _init_patterns(self):
        """Initialize pattern dictionaries for natural language processing"""
        
        # Basic time keywords
        self.basic_keywords = {
            'today': lambda: self.today,
            'tomorrow': lambda: self.today + timedelta(days=1),
            'yesterday': lambda: self.today - timedelta(days=1),
            'day after tomorrow': lambda: self.today + timedelta(days=2)
        }
        
        # Weekday patterns
        self.weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6,
            'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6
        }
        
        # Month patterns
        self.months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
            'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        
        # Comparison operators
        self.comparison_patterns = {
            'before': 'before',
            'after': 'after',
            'on or before': 'on_or_before',
            'on or after': 'on_or_after',
            'by': 'on_or_before',
            'until': 'on_or_before',
            'from': 'on_or_after',
            'since': 'on_or_after',
            'no later than': 'on_or_before',
            'no earlier than': 'on_or_after'
        }
        
        # Range patterns
        self.range_patterns = [
            r'between\s+(.+?)\s+and\s+(.+)',
            r'from\s+(.+?)\s+to\s+(.+)',
            r'(.+?)\s+to\s+(.+)',
            r'(.+?)\s+through\s+(.+)',
            r'(.+?)\s+-\s+(.+)'
        ]
        
        # Business time patterns
        self.business_periods = {
            'month end': lambda: self._get_month_end(),
            'month start': lambda: self._get_month_start(),
            'quarter end': lambda: self._get_quarter_end(),
            'quarter start': lambda: self._get_quarter_start(),
            'year end': lambda: self._get_year_end(),
            'year start': lambda: self._get_year_start(),
            'fiscal year end': lambda: self._get_fiscal_year_end(),
            'end of month': lambda: self._get_month_end(),
            'beginning of month': lambda: self._get_month_start(),
            'end of quarter': lambda: self._get_quarter_end(),
            'end of year': lambda: self._get_year_end()
        }
        
        # Fuzzy time patterns
        self.fuzzy_patterns = {
            'around': 3,  # +/- 3 days
            'roughly': 5,  # +/- 5 days
            'about': 3,
            'approximately': 5,
            'sometime': 7,
            'near': 2
        }
        
        # Overdue/late patterns
        self.overdue_patterns = [
            'overdue', 'late', 'past due', 'behind schedule',
            'delayed', 'missed', 'expired'
        ]
        
        # Holiday patterns (customize based on your business needs)
        self.holidays = {
            'christmas': lambda year: date(year, 12, 25),
            'new year': lambda year: date(year, 1, 1),
            'thanksgiving': lambda year: self._get_thanksgiving(year),
            'memorial day': lambda year: self._get_memorial_day(year),
            'labor day': lambda year: self._get_labor_day(year)
        }

    def _init_business_dates(self):
        """Initialize business calendar settings"""
        self.fiscal_year_start = 4  # April = fiscal year start (customize as needed)
        self.working_days = [0, 1, 2, 3, 4]  # Monday through Friday

    def filter_dataframe_by_time(self, df: pd.DataFrame, time_description: str, date_column: str) -> pd.DataFrame:
        """Enhanced filter method with comprehensive natural language support"""
        if date_column not in df.columns:
            raise TimeParsingError(f"Date column '{date_column}' not found in DataFrame")
        
        df = df.copy()
        df[date_column] = pd.to_datetime(df[date_column])
        
        # First, check for overdue/late orders
        if self._is_overdue_query(time_description):
            return df[df[date_column].dt.date < self.today]
        
        try:
            # Parse the time description to get date range
            start_date, end_date, comparison_type = self._parse_natural_language_time(time_description)
            
            # Apply the filter based on comparison type
            return self._apply_date_filter(df, date_column, start_date, end_date, comparison_type)
            
        except TimeParsingError:
            # Fall back to original simple parsing for backwards compatibility
            return self._legacy_filter(df, time_description, date_column)

    def _parse_natural_language_time(self, time_description: str) -> Tuple[Optional[date], Optional[date], str]:
        """Parse natural language time descriptions into date ranges"""
        time_desc_lower = time_description.lower().strip()
        
        # Check for range queries first
        range_result = self._parse_range_query(time_desc_lower)
        if range_result:
            return range_result
        
        # Check for comparison queries (before, after, etc.)
        comparison_result = self._parse_comparison_query(time_desc_lower)
        if comparison_result:
            return comparison_result
        
        # Check for basic keywords
        basic_result = self._parse_basic_keywords(time_desc_lower)
        if basic_result:
            return basic_result
        
        # Check for relative dates
        relative_result = self._parse_relative_dates(time_desc_lower)
        if relative_result:
            return relative_result
        
        # Check for specific dates
        specific_result = self._parse_specific_dates(time_desc_lower)
        if specific_result:
            return specific_result
        
        # Check for business periods
        business_result = self._parse_business_periods(time_desc_lower)
        if business_result:
            return business_result
        
        # Check for fuzzy references
        fuzzy_result = self._parse_fuzzy_references(time_desc_lower)
        if fuzzy_result:
            return fuzzy_result
        
        raise TimeParsingError(f"Could not understand the time description: '{time_description}'")

    def _parse_range_query(self, time_desc: str) -> Optional[Tuple[Optional[date], Optional[date], str]]:
        """Parse range queries like 'between X and Y', 'from X to Y'"""
        for pattern in self.range_patterns:
            match = re.search(pattern, time_desc, re.IGNORECASE)
            if match:
                start_str, end_str = match.groups()
                try:
                    start_date = self._parse_single_date_reference(start_str.strip())
                    end_date = self._parse_single_date_reference(end_str.strip())
                    return start_date, end_date, 'range'
                except TimeParsingError:
                    continue
                except:
                    continue
        return None

    def _parse_comparison_query(self, time_desc: str) -> Optional[Tuple[Optional[date], Optional[date], str]]:
        """Parse comparison queries like 'before X', 'after Y'"""
        for phrase, comp_type in self.comparison_patterns.items():
            if phrase in time_desc:
                # Extract the date part after the comparison phrase
                pattern = rf'{re.escape(phrase)}\s+(.+?)(?:\s+that|\s+which|$)'
                match = re.search(pattern, time_desc, re.IGNORECASE)
                if match:
                    date_str = match.group(1).strip()
                    try:
                        target_date = self._parse_single_date_reference(date_str)
                        if comp_type == 'before':
                            return None, target_date - timedelta(days=1), 'before'
                        elif comp_type == 'after':
                            return target_date + timedelta(days=1), None, 'after'
                        elif comp_type == 'on_or_before':
                            return None, target_date, 'on_or_before'
                        elif comp_type == 'on_or_after':
                            return target_date, None, 'on_or_after'
                    except:
                        continue
        return None

    def _parse_basic_keywords(self, time_desc: str) -> Optional[Tuple[Optional[date], Optional[date], str]]:
        """Parse basic keywords like 'today', 'tomorrow', 'this week'"""
        # Check for basic single-day keywords
        for keyword, date_func in self.basic_keywords.items():
            if keyword in time_desc:
                target_date = date_func()
                return target_date, target_date, 'exact'
        
        # Check for week references
        if 'this week' in time_desc:
            start, end = self._get_week_range(self.today)
            return start, end, 'range'
        elif 'next week' in time_desc:
            next_week_start = self.today + timedelta(days=(7 - self.today.weekday()))
            start, end = self._get_week_range(next_week_start)
            return start, end, 'range'
        elif 'last week' in time_desc:
            last_week_start = self.today - timedelta(days=self.today.weekday() + 7)
            start, end = self._get_week_range(last_week_start)
            return start, end, 'range'
        
        # Check for month references
        if 'this month' in time_desc:
            start, end = self._get_month_range(self.today.year, self.today.month)
            return start, end, 'range'
        elif 'next month' in time_desc:
            next_month = self.today.replace(day=1) + relativedelta(months=1)
            start, end = self._get_month_range(next_month.year, next_month.month)
            return start, end, 'range'
        elif 'last month' in time_desc:
            last_month = self.today.replace(day=1) - relativedelta(months=1)
            start, end = self._get_month_range(last_month.year, last_month.month)
            return start, end, 'range'
        
        return None

    def _parse_relative_dates(self, time_desc: str) -> Optional[Tuple[Optional[date], Optional[date], str]]:
        """Parse relative dates like 'in 30 days', '2 weeks from now'"""
        # Pattern for "in X days/weeks/months"
        pattern1 = r'in\s+(\d+)\s+(day|week|month)s?'
        match1 = re.search(pattern1, time_desc, re.IGNORECASE)
        if match1:
            value, unit = int(match1.group(1)), match1.group(2).lower()
            if 'day' in unit:
                target_date = self.today + timedelta(days=value)
            elif 'week' in unit:
                target_date = self.today + timedelta(weeks=value)
            elif 'month' in unit:
                target_date = self.today + relativedelta(months=value)
            return target_date, target_date, 'exact'
        
        # Pattern for "X days/weeks/months from now"
        pattern2 = r'(\d+)\s+(day|week|month)s?\s+from\s+now'
        match2 = re.search(pattern2, time_desc, re.IGNORECASE)
        if match2:
            value, unit = int(match2.group(1)), match2.group(2).lower()
            if 'day' in unit:
                target_date = self.today + timedelta(days=value)
            elif 'week' in unit:
                target_date = self.today + timedelta(weeks=value)
            elif 'month' in unit:
                target_date = self.today + relativedelta(months=value)
            return target_date, target_date, 'exact'
        
        # Pattern for "next X days/weeks/months"
        pattern3 = r'next\s+(\d+)\s+(day|week|month)s?'
        match3 = re.search(pattern3, time_desc, re.IGNORECASE)
        if match3:
            value, unit = int(match3.group(1)), match3.group(2).lower()
            if 'day' in unit:
                end_date = self.today + timedelta(days=value)
            elif 'week' in unit:
                end_date = self.today + timedelta(weeks=value)
            elif 'month' in unit:
                end_date = self.today + relativedelta(months=value)
            return self.today, end_date, 'range'
        
        return None

    def _parse_specific_dates(self, time_desc: str) -> Optional[Tuple[Optional[date], Optional[date], str]]:
        """Parse specific dates like 'December 25, 2024', 'Jan 1st'"""
        # Multiple date formats
        date_patterns = [
            r'(\d{4}-\d{1,2}-\d{1,2})',
            r'(\d{1,2}-\d{1,2}-\d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'([a-zA-Z]+\s+\d{1,2},?\s+\d{4})',
            r'(\d{1,2}\s+[a-zA-Z]+\s+\d{4})',
            r'([a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?)',
            r'(\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+)'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, time_desc, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1)
                    target_date = parse_date(date_str, dayfirst=True).date()
                    # If no year specified and date is in the past, assume next year
                    if target_date < self.today and len(date_str.split()) < 3:
                        target_date = target_date.replace(year=self.today.year + 1)
                    return target_date, target_date, 'exact'
                except:
                    continue
        
        return None

    def _parse_business_periods(self, time_desc: str) -> Optional[Tuple[Optional[date], Optional[date], str]]:
        """Parse business periods like 'month end', 'quarter end'"""
        for period, date_func in self.business_periods.items():
            if period in time_desc:
                target_date = date_func()
                return target_date, target_date, 'exact'
        return None

    def _parse_fuzzy_references(self, time_desc: str) -> Optional[Tuple[Optional[date], Optional[date], str]]:
        """Parse fuzzy references like 'around next week', 'roughly end of month'"""
        for fuzzy_word, tolerance in self.fuzzy_patterns.items():
            if fuzzy_word in time_desc:
                # Remove fuzzy word and parse the rest
                clean_desc = time_desc.replace(fuzzy_word, '').strip()
                try:
                    # Use a simple parser to avoid recursion
                    base_date = self._parse_single_date_reference(clean_desc)
                    # Single date - add tolerance
                    return (base_date - timedelta(days=tolerance), 
                           base_date + timedelta(days=tolerance), 'range')
                except:
                    continue
        return None
    
    def _parse_single_date_reference(self, date_str: str) -> date:
        """
        Parse a single date reference by leveraging the main natural language parser.
        This ensures that any time expression can be used as a boundary for a range or comparison.
        """
        date_str = date_str.strip().lower()
        
        # Check basic keywords first
        for keyword, date_func in self.basic_keywords.items():
            if keyword in date_str:
                return date_func()
        
        # Check for weekday references
        for day_name, day_num in self.weekdays.items():
            if day_name in date_str:
                return self._get_next_weekday(day_num)
        
        # Check for business periods
        for period, date_func in self.business_periods.items():
            if period in date_str:
                return date_func()
        
        # Handle relative dates like "next week", "last month"
        if 'next week' in date_str:
            return self.today + timedelta(days=(7 - self.today.weekday()))
        elif 'last week' in date_str:
            return self.today - timedelta(days=self.today.weekday() + 7)
        elif 'this week' in date_str:
            return self.today - timedelta(days=self.today.weekday())  # Start of this week
        elif 'next month' in date_str:
            next_month = self.today.replace(day=1) + relativedelta(months=1)
            return next_month
        elif 'last month' in date_str:
            last_month = self.today.replace(day=1) - relativedelta(months=1)
            return last_month
        elif 'this month' in date_str:
            return self.today.replace(day=1)  # Start of this month
        
        # Handle simple relative dates
        match = re.search(r'(\d+)\s+(day|week|month)s?\s+(ago|from\s+now)', date_str)
        if match:
            value, unit, direction = int(match.group(1)), match.group(2).lower(), match.group(3)
            if 'day' in unit:
                delta = timedelta(days=value)
            elif 'week' in unit:
                delta = timedelta(weeks=value)
            elif 'month' in unit:
                delta = relativedelta(months=value)
            
            if 'ago' in direction:
                return self.today - delta
            else:
                return self.today + delta
        
        # Try to parse as a specific date using dateutil
        try:
            parsed_date = parse_date(date_str, dayfirst=True).date()
            # If no year specified and date is in the past, assume next year
            if parsed_date < self.today and len(date_str.split()) < 3:
                parsed_date = parsed_date.replace(year=self.today.year + 1)
            return parsed_date
        except:
            pass
        
        raise TimeParsingError(f"Could not understand the date reference: '{date_str}'")

    def _is_overdue_query(self, time_description: str) -> bool:
        """Check if the query is asking for overdue/late orders"""
        time_desc_lower = time_description.lower()
        return any(pattern in time_desc_lower for pattern in self.overdue_patterns)

    def _apply_date_filter(self, df: pd.DataFrame, date_column: str, start_date: Optional[date], 
                          end_date: Optional[date], comparison_type: str) -> pd.DataFrame:
        """Apply the parsed date filter to the DataFrame"""
        if comparison_type == 'exact' and start_date:
            return df[df[date_column].dt.date == start_date]
        elif comparison_type == 'range':
            conditions = []
            if start_date:
                conditions.append(df[date_column].dt.date >= start_date)
            if end_date:
                conditions.append(df[date_column].dt.date <= end_date)
            if conditions:
                combined_condition = conditions[0]
                for condition in conditions[1:]:
                    combined_condition &= condition
                return df[combined_condition]
        elif comparison_type == 'before' and end_date:
            return df[df[date_column].dt.date <= end_date]
        elif comparison_type == 'after' and start_date:
            return df[df[date_column].dt.date >= start_date]
        elif comparison_type == 'on_or_before' and end_date:
            return df[df[date_column].dt.date <= end_date]
        elif comparison_type == 'on_or_after' and start_date:
            return df[df[date_column].dt.date >= start_date]
        
        return df

    def _legacy_filter(self, df: pd.DataFrame, time_description: str, date_column: str) -> pd.DataFrame:
        """Legacy filter method for backwards compatibility"""
        time_desc_lower = time_description.lower()
        today = date.today()

        if "today" in time_desc_lower: 
            return df[df[date_column].dt.date == today]
        if "tomorrow" in time_desc_lower: 
            return df[df[date_column].dt.date == today + timedelta(days=1)]
        if "day after tomorrow" in time_desc_lower: 
            return df[df[date_column].dt.date == today + timedelta(days=2)]
        
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

    # Helper methods for date calculations
    def _get_week_range(self, reference_date: date) -> Tuple[date, date]:
        """Get start and end of week for a reference date"""
        start = reference_date - timedelta(days=reference_date.weekday())
        end = start + timedelta(days=6)
        return start, end

    def _get_month_range(self, year: int, month: int) -> Tuple[date, date]:
        """Get start and end of month"""
        start = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end = date(year, month, last_day)
        return start, end

    def _get_next_weekday(self, target_weekday: int) -> date:
        """Get the next occurrence of a specific weekday"""
        days_ahead = target_weekday - self.today.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        return self.today + timedelta(days=days_ahead)

    def _get_month_end(self) -> date:
        """Get end of current month"""
        _, last_day = calendar.monthrange(self.today.year, self.today.month)
        return date(self.today.year, self.today.month, last_day)

    def _get_month_start(self) -> date:
        """Get start of current month"""
        return date(self.today.year, self.today.month, 1)

    def _get_quarter_end(self) -> date:
        """Get end of current quarter"""
        quarter = (self.today.month - 1) // 3 + 1
        last_month = quarter * 3
        _, last_day = calendar.monthrange(self.today.year, last_month)
        return date(self.today.year, last_month, last_day)

    def _get_quarter_start(self) -> date:
        """Get start of current quarter"""
        quarter = (self.today.month - 1) // 3 + 1
        first_month = (quarter - 1) * 3 + 1
        return date(self.today.year, first_month, 1)

    def _get_year_end(self) -> date:
        """Get end of current year"""
        return date(self.today.year, 12, 31)

    def _get_year_start(self) -> date:
        """Get start of current year"""
        return date(self.today.year, 1, 1)

    def _get_fiscal_year_end(self) -> date:
        """Get end of fiscal year (customize based on your fiscal year)"""
        if self.today.month >= self.fiscal_year_start:
            return date(self.today.year + 1, self.fiscal_year_start - 1, 
                       calendar.monthrange(self.today.year + 1, self.fiscal_year_start - 1)[1])
        else:
            return date(self.today.year, self.fiscal_year_start - 1,
                       calendar.monthrange(self.today.year, self.fiscal_year_start - 1)[1])

    def _get_thanksgiving(self, year: int) -> date:
        """Get Thanksgiving date (4th Thursday of November)"""
        nov_1 = date(year, 11, 1)
        first_thursday = 1 + (3 - nov_1.weekday()) % 7
        return date(year, 11, first_thursday + 21)

    def _get_memorial_day(self, year: int) -> date:
        """Get Memorial Day (last Monday of May)"""
        may_31 = date(year, 5, 31)
        last_monday = 31 - (may_31.weekday() + 2) % 7
        return date(year, 5, last_monday)

    def _get_labor_day(self, year: int) -> date:
        """Get Labor Day (first Monday of September)"""
        sep_1 = date(year, 9, 1)
        first_monday = 1 + (7 - sep_1.weekday()) % 7
        return date(year, 9, first_monday)

    def parse_duration_to_days(self, duration_str: str) -> int:
        """Parse duration strings to days (maintained for backwards compatibility)"""
        match = re.search(r'(\d+)\s*(day|week|month)', duration_str, re.IGNORECASE)
        if not match:
            raise TimeParsingError("Invalid duration format. Use 'X days/weeks/months'")
        value, unit = int(match.group(1)), match.group(2).lower()
        if 'day' in unit: return value
        if 'week' in unit: return value * 7
        if 'month' in unit: return value * 30
        return 0
    # In time_parser.py, ensure accurate day calculations
    def _calculate_days_from_today(self, target_date: date) -> int:
        """Calculate days between today and target date with clear logic"""
        today = date.today()
        return (target_date - today).days

    def _get_time_description(self, days_difference: int) -> str:
        """Provide clear time descriptions"""
        if days_difference < 0:
            return f"overdue by {abs(days_difference)} day(s)"
        elif days_difference == 0:
            return "due today"
        elif days_difference == 1:
            return "due tomorrow"
        else:
            return f"due in {days_difference} days"
    
    def extract_query_parameters(self, natural_query: str) -> Dict[str, Any]:
        """Extract query parameters from natural language query"""
        params = {}
        query_lower = natural_query.lower()
        
        # Extract item_type
        if 'make order' in query_lower or 'make item' in query_lower:
            params['item_type'] = 'make'
        elif 'buy order' in query_lower or 'buy item' in query_lower or 'purchase order' in query_lower:
            params['item_type'] = 'buy'
        
        # Extract reschedule_needed
        if any(pattern in query_lower for pattern in self.overdue_patterns):
            params['reschedule_needed'] = True
        elif 'reschedule' in query_lower or 'need rescheduling' in query_lower:
            params['reschedule_needed'] = True
        
        # Extract query_type
        if 'how many' in query_lower or 'count' in query_lower:
            params['query_type'] = 'count'
        else:
            params['query_type'] = 'list'
        
        # Extract time_description (everything else)
        time_desc = natural_query
        # Remove item_type references
        for phrase in ['make orders', 'make items', 'buy orders', 'buy items', 'purchase orders']:
            time_desc = re.sub(phrase, '', time_desc, flags=re.IGNORECASE)
        # Remove reschedule references
        for phrase in ['that need rescheduling', 'need reschedule', 'to reschedule']:
            time_desc = re.sub(phrase, '', time_desc, flags=re.IGNORECASE)
        # Remove count references
        time_desc = re.sub(r'how many|count', '', time_desc, flags=re.IGNORECASE)
        
        time_desc = time_desc.strip()
        if time_desc:
            params['time_description'] = time_desc
        
        return params