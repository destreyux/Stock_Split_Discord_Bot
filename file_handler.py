# file_handler.py
"""Functions for reading and writing data to files (CSV)."""
import json # Keep json import if using log_ai_response from ai_handler
import pandas as pd
import os
import config # Import constants

# --- save_to_json and load_from_json REMOVED as main script doesn't use them ---

def save_to_csv(data, filepath=config.FINAL_CSV_FILE_PATH):
    """Saves a list of dictionaries to a CSV file."""
    if not data:
        print("No data provided to save to CSV.")
        return False
    print(f"Attempting to save {len(data)} records to CSV '{filepath}'...")
    try:
        df = pd.DataFrame(data)
        # Add timestamp if not already present
        if 'scrape_timestamp' not in df.columns:
             now_ts = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
             # Insert timestamp at the beginning for better visibility
             df.insert(0, 'scrape_timestamp', now_ts)

        # Define desired column order (adjust as needed)
        desired_cols = ['scrape_timestamp', 'Ticker', 'Exchange', 'CompanyName', 'Ratio', 'ExDate', 'fractional_share_handling']
        # Ensure only existing columns are selected and ordered
        final_cols = [col for col in desired_cols if col in df.columns]
        extra_cols = [col for col in df.columns if col not in final_cols] # Keep any unexpected extra cols
        df = df[final_cols + extra_cols]

        dir_name = os.path.dirname(filepath)
        if dir_name: os.makedirs(dir_name, exist_ok=True)
        df.to_csv(filepath, index=False, encoding='utf-8')
        print(f"Successfully saved data to {filepath}")
        return True
    except Exception as e:
        print(f"Error: Could not save data to CSV '{filepath}': {e}")
        return False