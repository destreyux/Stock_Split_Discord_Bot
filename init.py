import pandas as pd
import datetime
import os
import time
import google.generativeai as genai
import json
import requests

# --- Selenium Imports ---
from selenium import webdriver
# ... (other selenium imports) ...
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

# --- Attempt to import configuration from main.py ---
try:
    import main
    print("Successfully imported configuration from main.py")
    if not hasattr(main, 'URL'): raise AttributeError("main.py is missing 'URL'")
    if not hasattr(main, 'GEMINI_API_KEY'): main.GEMINI_API_KEY = None
    if not hasattr(main, 'DISCORD_WEBHOOK_URL') or not main.DISCORD_WEBHOOK_URL:
        print("Warning: 'DISCORD_WEBHOOK_URL' not found or empty. Discord notifications will be skipped.")
        main.DISCORD_WEBHOOK_URL = None
except ImportError: exit("ERROR: Could not import 'main.py'.")
except AttributeError as e: exit(f"ERROR: In main.py: {e}")


# --- Main Variables & Configuration ---
TARGET_URL = main.URL
API_KEY = main.GEMINI_API_KEY
DISCORD_WEBHOOK_URL = main.DISCORD_WEBHOOK_URL
URL = TARGET_URL
if not URL: exit("Error: URL retrieved from main.py is empty.")
CSV_FILE_PATH = 'upcoming_splits.csv'
AI_MODEL_NAME = 'gemini-1.5-flash-latest'
# --- NEW: History file path ---
HISTORY_FILE_PATH = 'notified_splits_history.log'

# --- WebDriver Configuration ---
# ... (Choose WebDriver setup) ...

# --- Configure Gemini API ---
GEMINI_API_KEY = None
# ... (Gemini configure logic) ...
try: # Simplified configure logic
    if API_KEY: genai.configure(api_key=API_KEY); GEMINI_API_KEY=API_KEY; print(f"Gemini API configured for {AI_MODEL_NAME}.")
    else: print("No Gemini API Key. AI validation skipped.")
except Exception as e: print(f"Warning: Error configuring Gemini API: {e}"); GEMINI_API_KEY = None

# --- Helper Functions ---
def is_reverse_split(ratio_str):
    # ... (Keep is_reverse_split function) ...
    try: # Simplified logic from previous versions
        if not isinstance(ratio_str, str) or not ratio_str: return False
        ratio_str = ratio_str.strip(); parts = []
        if ':' in ratio_str: parts = ratio_str.split(':')
        elif '/' in ratio_str: parts = ratio_str.split('/')
        elif 'for' in ratio_str: parts = ratio_str.split('-for-')
        else: return False
        if len(parts) != 2: return False
        return float(parts[0].strip()) < float(parts[1].strip())
    except Exception: return False


def get_batch_ai_validation(reverse_split_list):
    # ... (Keep get_batch_ai_validation function using the simplified prompt/parsing) ...
    if not GEMINI_API_KEY: return {};
    if not reverse_split_list: return {}
    model = genai.GenerativeModel(AI_MODEL_NAME);
    # --- Using Simplified Prompt ---
    prompt_header = """
For each stock split listed below, will fractional shares resulting from the reverse split MOST LIKELY be handled by:
1. Rounding Up? OR 2. Cash-in-Lieu?
Base your answer on reliable info. If none found, state that.
Respond ONLY with the ticker symbol, followed by a colon and a space, then the result. Place each stock on a new line.
Use EXACTLY one of these phrases for the result:
- Rounding Up Likely
- Cash-in-Lieu Likely
- Insufficient Information
Example Format:\nXYZ: Cash-in-Lieu Likely\nABC: Insufficient Information
Stocks to analyze:
"""
    prompt_body = "";
    for i, split_info in enumerate(reverse_split_list): prompt_body += f"{i+1}. {split_info['ticker']} (...)\n" # Abbreviated for brevity
    full_prompt = prompt_header + prompt_body
    print(f"Sending simplified batch request to Gemini for {len(reverse_split_list)} reverse splits...")
    ai_results_map = {}; response_text = ""
    try: response = model.generate_content(full_prompt); response_text = response.text
    except Exception as e: print(f"Gemini API Error: {e}"); return {s['ticker']: "AI API Error" for s in reverse_split_list}
    # --- Simplified Parsing Logic ---
    print("Parsing simplified AI response...")
    response_lines = response_text.splitlines(); allowed_results = {"rounding up likely", "cash-in-lieu likely", "insufficient information"}
    for line in response_lines: # Simplified parsing loop
        parts = line.strip().split(":", 1);
        if len(parts) == 2:
            ticker, result = parts[0].strip(), parts[1].strip(); result_lower = result.lower()
            if result_lower in allowed_results:
                 final_result = result.replace("likely", "Likely").replace("information", "Information").replace("up","Up").replace("in-lieu","in-Lieu") # Attempt to fix capitalization
                 ai_results_map[ticker] = final_result
            else: ai_results_map[ticker] = "AI Response Unclear"
    missing_tickers = {s['ticker'] for s in reverse_split_list} - set(ai_results_map.keys())
    if missing_tickers: print(f"Warning: AI parsing incomplete. Missing: {missing_tickers}"); [ai_results_map.setdefault(t, "AI Response Parse Error") for t in missing_tickers]
    print(f"Finished batch AI processing. Found results for {len(ai_results_map)} tickers.")
    return ai_results_map


def send_discord_notification(webhook_url, split_data):
    # ... (Keep send_discord_notification function exactly as before) ...
    if not webhook_url: return False
    headers = {"Content-Type": "application/json"}
    payload = {"embeds": [{"title": "📈 Upcoming Stock Split", "color": 3447003, "fields": [ {"name": "Ticker", "value": split_data.get('Ticker', 'N/A'), "inline": False}, {"name": "Company", "value": split_data.get('CompanyName', 'N/A'), "inline": False}, {"name": "Ratio", "value": split_data.get('Ratio', 'N/A'), "inline": False}, {"name": "Buy Before (Ex-Date)", "value": split_data.get('ExDate', 'N/A'), "inline": False}, {"name": "Fractional Handling", "value": split_data.get('fractional_share_handling', 'N/A'), "inline": False} ], "footer": {"text": "Source: Automated Stock Split Script"}, "timestamp": datetime.datetime.utcnow().isoformat() }]}
    try: response = requests.post(webhook_url, headers=headers, json=payload, timeout=10); response.raise_for_status(); return True
    except requests.exceptions.RequestException as e: print(f"Error sending Discord notification for {split_data.get('Ticker', 'N/A')}: {e}"); return False
    except Exception as e: print(f"Unexpected error during Discord notification: {e}"); return False


# --- NEW FUNCTION: Load/Save Notification History ---
def load_notified_history(filepath):
    """Loads previously notified split keys from a file."""
    notified = set()
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    notified.add(line.strip())
            print(f"Loaded {len(notified)} entries from notification history.")
    except Exception as e:
        print(f"Warning: Could not load notification history from {filepath}: {e}")
        print("Starting with empty history for this run.")
    return notified

def save_notified_history(filepath, notified_set):
    """Saves the updated set of notified split keys to a file."""
    print(f"Attempting to save {len(notified_set)} entries to notification history...")
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for key in sorted(list(notified_set)): # Save sorted list for readability
                f.write(key + '\n')
        print(f"Successfully saved notification history to {filepath}")
    except Exception as e:
        print(f"Error: Could not save notification history to {filepath}: {e}")
        print("Notifications for this run might be repeated next time.")

# --- Selenium Main Scraping Logic ---
initial_records = []
reverse_splits_to_analyze = []
driver = None
final_scraped_data = []
processed_count_final = 0
# --- Load History at Start ---
notified_keys_history = load_notified_history(HISTORY_FILE_PATH)

print("\nInitializing Selenium WebDriver...")
try:
    # --- Setup WebDriver Options & Initialize Driver ---
    # ... (WebDriver setup) ...
    options = webdriver.ChromeOptions(); # ... (add your options) ...
    options.add_argument('--headless'); # ... etc
    driver = webdriver.Chrome(options=options) # Assuming driver in PATH

    # --- Navigate & Wait ---
    # ... (Navigate and Wait logic) ...
    driver.get(URL); wait_time = 25; # ... (rest of wait logic) ...
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
    try: tbody = table_element.find_element(By.TAG_NAME, "tbody"); rows = tbody.find_elements(By.TAG_NAME, "tr"); print(f"Found {len(rows)} <tr> elements.")
    except NoSuchElementException: print("Fatal Error: Could not find <tbody>."); raise
    for i, row_element in enumerate(rows):
        try: cells = row_element.find_elements(By.TAG_NAME, "td"); current_row_values = [c.get_attribute('data-val').strip() if c.get_attribute('data-val') else '' for c in cells]
        except StaleElementReferenceException: print(f"Warning: Row {i} stale. Skipping."); continue
        except Exception as e: print(f"Warning: Error extracting cells row {i}: {e}. Skipping."); continue
        if current_row_values: all_row_data_values.append(current_row_values)
    print(f"Successfully extracted data from {len(all_row_data_values)} rows.")


    # --- *FIRST PASS*: Process rows, stop if date past/present ---
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
                if ex_date_obj <= today_date: stop_processing = True; print(f"  Stopping data collection: Ex-Date {ex_date_str} <= today.")
            except Exception: pass

        if stop_processing: break

        try: # Extract remaining values
            ticker_val = row_values[TICKER_IDX]; company_val = row_values[COMPANY_NAME_IDX]; ratio_val = row_values[RATIO_IDX]
            ex_date_cleaned = ex_date_obj.strftime('%Y-%m-%d') if ex_date_obj else None
        except IndexError: continue
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
    print("Second pass: Merging AI results...")
    final_scraped_data = [] # Contains only future splits ready for saving/notifying
    processed_count_final = 0

    for record in initial_records: # Already filtered for future dates in first pass
        ticker = record['Ticker']
        if record['fractional_share_handling'] == 'Pending AI Analysis':
            record['fractional_share_handling'] = ai_results.get(ticker, 'AI Analysis Failed/Missing')

        final_scraped_data.append(record) # Add all records processed before stop
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
    else:
        print(f"\nNo records with future Ex-Dates found/processed to save. CSV file not updated.")


    # --- Send Discord Notifications (Checking History) ---
    notifications_sent = 0
    notifications_skipped = 0
    notifications_failed = 0
    # Use a copy of the loaded history set, we'll update this if sends are successful
    current_run_notified_keys = notified_keys_history.copy()

    if final_scraped_data and DISCORD_WEBHOOK_URL:
        print(f"\nChecking {len(final_scraped_data)} potential notifications against history...")
        for record in final_scraped_data:
            # --- Create unique key ---
            notification_key = f"{record.get('Ticker', 'UNKNOWN')}_{record.get('ExDate', 'NODATE')}"

            # --- Check if already notified ---
            if notification_key in notified_keys_history:
                # print(f"  Skipping notification for {notification_key}: Already notified.") # Optional debug
                notifications_skipped += 1
                continue # Move to the next record

            # --- If not notified, attempt to send ---
            print(f"  Attempting notification for new split: {notification_key}")
            if send_discord_notification(DISCORD_WEBHOOK_URL, record):
                 notifications_sent += 1
                 # --- Add key to current run's set upon successful send ---
                 current_run_notified_keys.add(notification_key)
            else:
                 notifications_failed += 1
                 # Optional: Decide if you want to retry failed notifications later?
                 # For now, we don't add to history if it failed.

            time.sleep(1.5) # IMPORTANT: Wait between Discord posts

        print(f"Finished sending Discord notifications. New Sent: {notifications_sent}, Skipped (Previously Sent): {notifications_skipped}, Failed: {notifications_failed}")

        # --- Update the history set for next time ---
        # Assign the potentially updated set back to the main variable
        notified_keys_history = current_run_notified_keys

    elif not DISCORD_WEBHOOK_URL:
         print("\nSkipping Discord notifications: Webhook URL not configured.")
    else:
         print("\nSkipping Discord notifications: No data processed to send.")


except TimeoutException: print("Script aborted due to timeout waiting for page elements.")
except Exception as e:
    print(f"\nFatal Error: An unexpected error occurred during the Selenium process.")
    print(f"Error details: {e}")
    import traceback
    traceback.print_exc()
finally:
    # --- Save History at End ---
    if 'notified_keys_history' in locals(): # Check if the variable exists (it should)
        save_notified_history(HISTORY_FILE_PATH, notified_keys_history)
    else:
        print("Warning: Notification history variable not found, cannot save history.")

    # --- Ensure the browser is closed ---
    if driver: print("Closing Selenium WebDriver..."); driver.quit(); print("WebDriver closed.")