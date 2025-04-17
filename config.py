# config.py
"""Configuration settings and constants."""
import os
# Removed By import as it's not needed without Google search selectors
# from selenium.webdriver.common.by import By

# --- File Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Final output CSV path
FINAL_CSV_FILE_PATH = os.path.join(BASE_DIR, 'analyzed_upcoming_splits.csv')
# Log for raw AI responses
AI_LOG_FILE_PATH = os.path.join(BASE_DIR, 'gemini_api_raw_responses.jsonl')
# History file (optional for potential future notification integration)
HISTORY_FILE_PATH = os.path.join(BASE_DIR, 'notified_splits_history.log')


# --- AI Configuration ---
AI_MODEL_NAME = 'gemini-1.5-flash-latest' # Or your preferred model
AI_REQUEST_TEMPERATURE = 0.2 # Lower temp for more focused response

# --- Scraping Configuration ---
SELENIUM_WAIT_TIME = 30 # Seconds to wait for initial table elements
# --- Discord Rate Limit ---
DISCORD_RATE_LIMIT_DELAY = 2.0

# --- Table Column Indices ---
# !!! VERIFY THESE INDICES based on the target website's table structure !!!
TICKER_IDX = 0
COMPANY_NAME_IDX = 2
RATIO_IDX = 3
EX_DATE_IDX = 4
# Optional: If exchange is directly in the table, set its index. Otherwise, None.
EXCHANGE_IDX = None # e.g., 1 if it's the second column

# --- AI Response Phrases ---
OUTPUT_ROUND_UP = "Rounding Up Likely"
OUTPUT_CASH = "Cash-in-Lieu Likely"
OUTPUT_UNKNOWN = "Unable to Determine"
CLASSIFICATION_PHRASES = [OUTPUT_ROUND_UP, OUTPUT_CASH, OUTPUT_UNKNOWN]