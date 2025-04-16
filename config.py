# config.py
"""Configuration settings and constants for the stock split checker."""

import os

# --- File Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Get directory of the script
CSV_FILE_PATH = os.path.join(BASE_DIR, 'upcoming_splits.csv')
HISTORY_FILE_PATH = os.path.join(BASE_DIR, 'notified_splits_history.log')
AI_LOG_FILE_PATH = os.path.join(BASE_DIR, 'gemini_api_raw_responses.jsonl')

# --- AI Configuration ---
AI_MODEL_NAME = 'gemini-1.5-flash-latest' # Or your preferred model

# --- Scraping Configuration ---
SELENIUM_WAIT_TIME = 30 # Seconds to wait for elements

# --- Table Column Indices ---
# !!! VERIFY THESE INDICES based on the target website's table structure !!!
TICKER_IDX = 0
COMPANY_NAME_IDX = 2
RATIO_IDX = 3
EX_DATE_IDX = 4
# Optional: If exchange is directly in the table, set its index. Otherwise, None.
EXCHANGE_IDX = None # e.g., 1 if it's the second column

# --- Discord Configuration ---
DISCORD_RATE_LIMIT_DELAY = 2.0 # Seconds between notifications

# --- AI Response Phrases ---
OUTPUT_ROUND_UP = "Rounding Up Likely"
OUTPUT_CASH = "Cash-in-Lieu Likely"
OUTPUT_UNKNOWN = "Unable to Determine"
CLASSIFICATION_PHRASES = [OUTPUT_ROUND_UP, OUTPUT_CASH, OUTPUT_UNKNOWN]