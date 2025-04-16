import pandas as pd
import datetime
import os
import time
import google.generativeai as genai
import json
import requests # <-- Import requests library

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

# Optional: if using webdriver-manager
# from webdriver_manager.chrome import ChromeDriverManager

# --- Attempt to import configuration from main.py ---
try:
    import main
    print("Successfully imported configuration from main.py")
    if not hasattr(main, 'URL'): raise AttributeError("main.py is missing 'URL'")
    if not hasattr(main, 'GEMINI_API_KEY'): main.GEMINI_API_KEY = None
    # --- Add check for Discord Webhook URL ---
    if not hasattr(main, 'DISCORD_WEBHOOK_URL') or not main.DISCORD_WEBHOOK_URL:
        print("Warning: 'DISCORD_WEBHOOK_URL' not found or empty in main.py. Discord notifications will be skipped.")
        main.DISCORD_WEBHOOK_URL = None # Set to None to skip notifications
    # --- End check ---
except ImportError: exit("ERROR: Could not import 'main.py'.")
except AttributeError as e: exit(f"ERROR: In main.py: {e}")


# --- Main Variables (Loaded from main.py) ---
TARGET_URL = main.URL
API_KEY = main.GEMINI_API_KEY
DISCORD_WEBHOOK_URL = main.DISCORD_WEBHOOK_URL # Get webhook URL

# --- Configuration (Using Variables from main.py) ---
URL = TARGET_URL
if not URL: exit("Error: URL retrieved from main.py is empty.")
CSV_FILE_PATH = 'upcoming_splits.csv'
AI_MODEL_NAME = 'gemini-1.5-flash-latest'

# --- WebDriver Configuration ---
# ... (Choose ONE WebDriver setup option) ...

# --- Configure Gemini API ---
GEMINI_API_KEY = None
try:
    if API_KEY:
        GEMINI_API_KEY = API_KEY
        genai.configure(api_key=GEMINI_API_KEY)
        print(f"Gemini API configured successfully for model {AI_MODEL_NAME}.")
    else: print("No Gemini API Key provided. AI validation will be skipped.")
except Exception as e: print(f"Warning: Error configuring Gemini API: {e}"); GEMINI_API_KEY = None

# --- Helper Functions ---
def is_reverse_split(ratio_str):
    # ... (Keep the robust is_reverse_split function as before) ...
    try: # Robust version
        if not isinstance(ratio_str, str) or not ratio_str: return False
        ratio_str = ratio_str.strip()
        parts = []; # ... (rest of parsing logic) ...
        if ':' in ratio_str: parts = ratio_str.split(':')
        elif '/' in ratio_str: parts = ratio_str.split('/')
        elif 'for' in ratio_str: parts = ratio_str.split('-for-')
        else: return False
        if len(parts) != 2: return False
        num_part = float(parts[0].strip()); den_part = float(parts[1].strip())
        return num_part < den_part
    except Exception: return False

def get_batch_ai_validation(reverse_split_list):
    # ... (Keep the get_batch_ai_validation function exactly as before, using the prompt you prefer) ...
    # --- Using Simplified Prompt ---
    if not GEMINI_API_KEY: return {};
    if not reverse_split_list: return {}
    model = genai.GenerativeModel(AI_MODEL_NAME);
    prompt_header = """
For each stock split listed below, will fractional shares resulting from the reverse split MOST LIKELY be handled by:
1. Rounding Up (to the nearest whole share)? OR 2. Cash-in-Lieu (payment for the fraction)?
Base your answer on the most reliable information available. If no reliable information is found, state that.
Respond ONLY with the ticker symbol, followed by a colon and a space, then the result. Place each stock on a new line.
Use EXACTLY one of these phrases for the result:
- Rounding Up Likely
- Cash-in-Lieu Likely
- Insufficient Information
Example Response Format:\nXYZ: Cash-in-Lieu Likely\nABC: Rounding Up Likely\nDEF: Insufficient Information
Stocks to analyze:
"""
    prompt_body = "";
    for i, split_info in enumerate(reverse_split_list): prompt_body += f"{i+1}. {split_info['ticker']} ({split_info['company_name']}, Ratio: {split_info['ratio']}, Ex-Date: {split_info['ex_date'] or 'N/A'})\n"
    full_prompt = prompt_header + prompt_body
    print(f"Sending simplified batch request to Gemini for {len(reverse_split_list)} reverse splits...")
    ai_results_map = {}; response_text = ""
    try:
        response = model.generate_content(full_prompt); response_text = response.text
        # print(f"--- Raw Batch AI Response ---\n{response_text}\n--------------------------") # DEBUG
    except Exception as e: print(f"Gemini API Error during batch request: {e}"); return {s['ticker']: "AI API Error" for s in reverse_split_list}
    # --- Simplified Parsing Logic ---
    print("Parsing simplified AI response...")
    response_lines = response_text.splitlines(); allowed_results = {"rounding up likely", "cash-in-lieu likely", "insufficient information"}
    for line_num, line in enumerate(response_lines):
        line_stripped = line.strip()
        if not line_stripped: continue
        if ":" in line_stripped:
            parts = line_stripped.split(":", 1);
            if len(parts) == 2:
                ticker = parts[0].strip(); result = parts[1].strip(); result_lower = result.lower()
                if result_lower in allowed_results:
                    if result_lower == "rounding up likely": final_result = "Round Up Likely"
                    elif result_lower == "cash-in-lieu likely": final_result = "Cash-in-Lieu Likely"
                    else: final_result = "Insufficient Information"
                    ai_results_map[ticker] = final_result
                else: ai_results_map[ticker] = "AI Response Unclear" # Assign specific status
    print("Finished simplified parsing.")
    parsed_tickers = set(ai_results_map.keys()); requested_tickers = {s['ticker'] for s in reverse_split_list}; missing_tickers = requested_tickers - parsed_tickers
    if missing_tickers: print(f"Warning: Final check - AI response parsing incomplete. Missing results for: {missing_tickers}"); [ai_results_map.setdefault(t, "AI Response Parse Error") for t in missing_tickers]
    print(f"Finished batch AI processing. Found results for {len(ai_results_map)} tickers.")
    return ai_results_map


# --- NEW FUNCTION: Send Discord Notification ---
def send_discord_notification(webhook_url, split_data):
    """Sends a single stock split notification to Discord."""
    if not webhook_url:
        # print("Skipping Discord notification: Webhook URL not configured.") # Can be noisy
        return False # Indicate URL was missing

    headers = {"Content-Type": "application/json"}
    # Construct the embed payload
    payload = {
        "embeds": [{
            "title": "📈 Upcoming Stock Split",
            "color": 3447003, # Power BI blue
            "fields": [
                {"name": "Ticker", "value": split_data.get('Ticker', 'N/A'), "inline": False},
                {"name": "Company", "value": split_data.get('CompanyName', 'N/A'), "inline": False},
                {"name": "Ratio", "value": split_data.get('Ratio', 'N/A'), "inline": False},
                {"name": "Buy Before (Ex-Date)", "value": split_data.get('ExDate', 'N/A'), "inline": False},
                {"name": "Fractional Handling", "value": split_data.get('fractional_share_handling', 'N/A'), "inline": False}
            ],
            "footer": {"text": "Source: Automated Stock Split Script"},
            "timestamp": datetime.datetime.utcnow().isoformat() # Use UTC timestamp
        }]
    }

    try:
        response = requests.post(webhook_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        # print(f"Successfully sent notification for {split_data.get('Ticker', 'N/A')}") # Optional success log
        return True
    except requests.exceptions.Timeout:
        print(f"Error sending Discord notification for {split_data.get('Ticker', 'N/A')}: Request timed out.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord notification for {split_data.get('Ticker', 'N/A')}: {e}")
        # Check for specific rate limit errors if possible (Discord uses 429)
        if e.response is not None and e.response.status_code == 429:
             print("Discord rate limit hit. Consider increasing sleep time.")
             # You might want to re-raise or handle this specifically
        return False
    except Exception as e:
        print(f"An unexpected error occurred during Discord notification for {split_data.get('Ticker', 'N/A')}: {e}")
        return False


# --- Selenium Main Scraping Logic ---
initial_records = []
reverse_splits_to_analyze = []
driver = None
final_scraped_data = [] # Define earlier for broader scope
processed_count_final = 0

print("\nInitializing Selenium WebDriver...")
try:
    # --- Setup WebDriver Options & Initialize Driver ---
    options = webdriver.ChromeOptions(); # ... (add your options) ...
    options.add_argument('--headless'); options.add_argument('--disable-gpu'); # ... etc
    driver = webdriver.Chrome(options=options) # Assuming driver in PATH

    print(f"Navigating to URL: {URL}")
    driver.get(URL)

    # --- Wait for table ---
    # ... (Wait logic) ...
    wait_time = 25; # ... (rest of wait logic) ...
    try: table_element = WebDriverWait(driver, wait_time).until(EC.presence_of_element_located((By.ID, "latest_splits"))); WebDriverWait(table_element, wait_time).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "tbody tr"))); print("Table content detected.")
    except TimeoutException as e: print(f"Error: Timed out waiting for table content."); raise

    # --- Extract Headers (Reference Only) ---
    # ... (Header extraction) ...
    try: thead = table_element.find_element(By.TAG_NAME, "thead"); headers = [th.text.strip() for th in thead.find_elements(By.TAG_NAME, "th")]; print(f"Extracted headers: {headers}")
    except Exception: print("Warning: Could not find/parse headers.")

    # --- Extract ALL row data first ---
    all_row_data_values = []
    print("Extracting data-val from all rows...")
    # ... (Extraction logic) ...
    try: tbody = table_element.find_element(By.TAG_NAME, "tbody"); rows = tbody.find_elements(By.TAG_NAME, "tr"); print(f"Found {len(rows)} <tr> elements initially.")
    except NoSuchElementException: print("Fatal Error: Could not find <tbody>."); raise
    for i, row_element in enumerate(rows):
        try: cells = row_element.find_elements(By.TAG_NAME, "td"); current_row_values = [c.get_attribute('data-val').strip() if c.get_attribute('data-val') else '' for c in cells]
        except StaleElementReferenceException: print(f"Warning: Row {i} stale. Skipping."); continue
        except Exception as e: print(f"Warning: Error extracting cells row {i}: {e}. Skipping."); continue
        if current_row_values: all_row_data_values.append(current_row_values)
    print(f"Successfully extracted data from {len(all_row_data_values)} rows.")


    # --- *FIRST PASS*: Process rows, filter by date, identify reverse splits ---
    print("First pass: Processing rows, stopping if Ex-Date is past/present...")
    # --- !!! VERIFY AND UPDATE THESE INDICES !!! ---
    TICKER_IDX = 0; COMPANY_NAME_IDX = 2; RATIO_IDX = 3; EX_DATE_IDX = 4
    required_indices = [TICKER_IDX, COMPANY_NAME_IDX, RATIO_IDX, EX_DATE_IDX]
    MIN_EXPECTED_COLUMNS = max(required_indices) + 1
    # --- End Index Definitions ---
    today_date = datetime.date.today(); stop_processing = False; first_pass_processed_count = 0

    for i, row_values in enumerate(all_row_data_values):
        first_pass_processed_count = i + 1
        # print(f"DEBUG - Row {i} Values: {row_values}") # Keep for index verification

        if not row_values or all(v == '' for v in row_values): continue
        if len(row_values) < MIN_EXPECTED_COLUMNS: continue

        ex_date_str = row_values[EX_DATE_IDX]; ex_date_obj = None
        if ex_date_str and isinstance(ex_date_str, str) and ex_date_str.upper() != 'N/A':
            try:
                ex_date_obj = datetime.datetime.strptime(ex_date_str, '%Y-%m-%d').date()
                if ex_date_obj <= today_date: stop_processing = True; print(f"  Stopping data collection at row {i}: Ex-Date {ex_date_str} is today or past.")
            except Exception: pass # Ignore parse errors for stopping check, proceed

        if stop_processing: break

        try:
            ticker_val = row_values[TICKER_IDX]; company_val = row_values[COMPANY_NAME_IDX]; ratio_val = row_values[RATIO_IDX]
            ex_date_cleaned = ex_date_obj.strftime('%Y-%m-%d') if ex_date_obj else None
        except IndexError: print(f"Row {i} skipped: IndexError. Data: {row_values}"); continue
        essential_values = [ticker_val, company_val, ratio_val, ex_date_cleaned]
        if not all(v for v in essential_values if v is not None): continue

        record = {'Ticker': ticker_val, 'CompanyName': company_val, 'Ratio': ratio_val, 'ExDate': ex_date_cleaned, 'fractional_share_handling': 'N/A (Forward Split or Pending AI)'}
        if is_reverse_split(ratio_val):
            record['fractional_share_handling'] = 'Pending AI Analysis'
            reverse_splits_to_analyze.append({'ticker': ticker_val, 'company_name': company_val, 'ratio': ratio_val, 'ex_date': ex_date_cleaned})
        initial_records.append(record)

    print(f"Finished first pass. Processed {first_pass_processed_count} rows before potential stop.")

    # --- Make the BATCH AI Call ---
    ai_results = {}
    if reverse_splits_to_analyze:
        print(f"Found {len(reverse_splits_to_analyze)} reverse splits to analyze.")
        ai_results = get_batch_ai_validation(reverse_splits_to_analyze)
    else: print("No reverse splits identified for AI analysis.")

    # --- *SECOND PASS*: Merge AI results & Prepare Final Data ---
    # (No date filtering needed here, already done)
    print("Second pass: Merging AI results...")
    final_scraped_data = [] # This list will contain only data to be saved/notified
    processed_count_final = 0

    for record in initial_records: # Loop through records collected *before* the stop
        ticker = record['Ticker']
        if record['fractional_share_handling'] == 'Pending AI Analysis':
            record['fractional_share_handling'] = ai_results.get(ticker, 'AI Analysis Failed/Missing')

        final_scraped_data.append(record) # Add all potentially updated future records
        processed_count_final += 1

    # --- Save to CSV ---
    if final_scraped_data:
        df = pd.DataFrame(final_scraped_data)
        df['scrape_timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        desired_cols = ['scrape_timestamp', 'Ticker', 'CompanyName', 'Ratio', 'ExDate', 'fractional_share_handling']
        final_cols = [col for col in desired_cols if col in df.columns]
        extra_cols = [col for col in df.columns if col not in final_cols]
        df = df[final_cols + extra_cols]
        try:
             df.to_csv(CSV_FILE_PATH, index=False, encoding='utf-8')
             print(f"\nSaved {processed_count_final} records with future Ex-Dates to {CSV_FILE_PATH}")
        except Exception as csv_err:
             print(f"\nError saving data to CSV '{CSV_FILE_PATH}': {csv_err}")
             # Continue to notification attempt even if save fails? Or stop? Decide based on need.
    else:
        print(f"\nNo records with future Ex-Dates found/processed to save. CSV file not updated.")


    # --- Send Discord Notifications (Loop through final data) ---
    notifications_sent = 0
    notifications_failed = 0
    if final_scraped_data and DISCORD_WEBHOOK_URL: # Only proceed if there's data AND a URL
        print(f"\nSending {len(final_scraped_data)} notifications to Discord...")
        for record in final_scraped_data:
            if send_discord_notification(DISCORD_WEBHOOK_URL, record):
                 notifications_sent += 1
            else:
                 notifications_failed += 1
            time.sleep(1.5) # IMPORTANT: Wait between Discord posts to avoid rate limits (1.5 seconds is safer)
        print(f"Finished sending Discord notifications. Sent: {notifications_sent}, Failed: {notifications_failed}")
    elif not DISCORD_WEBHOOK_URL:
         print("\nSkipping Discord notifications: Webhook URL not configured in main.py.")
    else:
         print("\nSkipping Discord notifications: No data to send.")


except TimeoutException: print("Script aborted due to timeout waiting for page elements.")
except Exception as e:
    print(f"\nFatal Error: An unexpected error occurred during the Selenium process.")
    print(f"Error details: {e}")
    import traceback
    traceback.print_exc()
finally:
    if driver: print("Closing Selenium WebDriver..."); driver.quit(); print("WebDriver closed.")