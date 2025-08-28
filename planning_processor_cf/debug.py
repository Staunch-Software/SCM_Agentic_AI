# Debug script to identify rescheduling calculation issues

import pandas as pd
from datetime import datetime, date, timedelta
import json

def debug_rescheduling_calculation():
    """
    Comprehensive debug function to identify the root cause of the rescheduling issue
    """
    
    # Test data based on your screenshot
    test_order = {
        'planned_order_id': 'PO-CAR-000001',
        'item_name': 'Test Item',
        'suggested_due_date': '2025-09-05'  # From your screenshot
    }
    
    print("=== RESCHEDULING DEBUG ANALYSIS ===")
    print(f"Order ID: {test_order['planned_order_id']}")
    print(f"Suggested Due Date: {test_order['suggested_due_date']}")
    
    # Get current date
    current_date = date.today()
    print(f"Current Date: {current_date}")
    
    # Test different parsing methods
    print("\n--- DATE PARSING TESTS ---")
    
    # Method 1: pandas to_datetime then .date()
    try:
        suggested_date_pd = pd.to_datetime(test_order['suggested_due_date']).date()
        days_diff_pd = (suggested_date_pd - current_date).days
        print(f"Method 1 (pandas): {suggested_date_pd}, Days difference: {days_diff_pd}")
    except Exception as e:
        print(f"Method 1 failed: {e}")
    
    # Method 2: Direct datetime parsing
    try:
        suggested_date_dt = datetime.strptime(test_order['suggested_due_date'], '%Y-%m-%d').date()
        days_diff_dt = (suggested_date_dt - current_date).days
        print(f"Method 2 (datetime): {suggested_date_dt}, Days difference: {days_diff_dt}")
    except Exception as e:
        print(f"Method 2 failed: {e}")
    
    # Method 3: pandas without .date() conversion (your current bug)
    try:
        suggested_date_bug = pd.to_datetime(test_order['suggested_due_date'])
        days_diff_bug = (suggested_date_bug - current_date).days
        print(f"Method 3 (BUGGY): {suggested_date_bug}, Days difference: {days_diff_bug}")
    except Exception as e:
        print(f"Method 3 failed: {e}")
    
    print("\n--- ELIGIBILITY LOGIC TEST ---")
    
    # Test with correct calculation
    correct_days = days_diff_dt
    print(f"Correct days difference: {correct_days}")
    
    if correct_days <= 0:
        status = "Postpone Only (Overdue)"
        can_prepone = False
        recommendation = "Can only postpone - order is due today or overdue"
    elif correct_days == 1:
        status = "Postpone Only (Due Tomorrow)"
        can_prepone = False
        recommendation = "Can only postpone - order is due tomorrow"
    else:
        status = "Prepone/Postpone"
        can_prepone = True
        max_prepone = correct_days - 1
        recommendation = f"Can prepone up to {max_prepone} days or postpone any number of days"
    
    print(f"Status: {status}")
    print(f"Can Prepone: {can_prepone}")
    print(f"Recommendation: {recommendation}")
    
    print("\n--- EXPECTED OUTPUT STRUCTURE ---")
    
    # What the analyze_rescheduling_eligibility should return
    expected_analysis = {
        'planned_order_id': test_order['planned_order_id'],
        'item_name': test_order['item_name'],
        'current_date': str(current_date),
        'suggested_due_date': test_order['suggested_due_date'],
        'days_from_today': correct_days,
        'can_prepone': can_prepone,
        'can_postpone': True,
        'max_prepone_days': max(0, correct_days - 1) if correct_days > 1 else 0,
        'status': 'overdue_or_today' if correct_days <= 0 else 'tomorrow' if correct_days == 1 else 'future',
        'recommendation': recommendation
    }
    
    print(json.dumps(expected_analysis, indent=2))
    
    print("\n--- SYSTEM DATE INFO ---")
    print(f"Today's date: {date.today()}")
    print(f"Today's datetime: {datetime.now()}")
    print(f"Timezone info: Check if your system/server timezone is correct")
    
    print("\n--- DEBUGGING CHECKLIST ---")
    print("1. ✓ Check if pandas datetime vs Python date mixing is the issue")
    print("2. ✓ Verify current date calculation")
    print("3. ✓ Test eligibility logic")
    print("4. ⚠️  Check if your CSV file has correct date format")
    print("5. ⚠️  Verify timezone settings")
    print("6. ⚠️  Check if the suggested_due_date in your data is actually 2025-09-05")

def debug_csv_data():
    """
    Function to debug the actual CSV data structure
    """
    print("\n=== CSV DATA DEBUG ===")
    print("Add this to your data_service.py to debug:")
    print("""
    def debug_data_load(self):
        df = self.load_data()
        print("DataFrame columns:", df.columns.tolist())
        print("DataFrame dtypes:", df.dtypes)
        print("Sample suggested_due_date values:", df['suggested_due_date'].head().tolist())
        print("Sample row for PO-CAR-000001:")
        sample = df[df['planned_order_id'] == 'PO-CAR-000001']
        if not sample.empty:
            print(sample[['planned_order_id', 'suggested_due_date']].to_dict('records'))
        return df
    """)

# Run the debug
if __name__ == "__main__":
    debug_rescheduling_calculation()
    debug_csv_data()