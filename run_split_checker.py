# run_split_checker.py
"""
Main script:
1. Scrapes upcoming splits.
2. Enriches with exchange info.
3. Sends batch request to AI for reverse split fractional analysis.
4. Merges AI results.
5. Saves final analyzed data to CSV.
Includes debugging prints for Discord notifications.
"""
import pandas as pd
import datetime
import time
import os
import sys

# --- Import configuration and modules ---
try:
    import main as secrets        # Your secrets (API keys, URLs)
    import config               # General settings and constants
    from scraper import setup_driver, scrape_split_data # Selenium functions
    from data_utils import get_exchange_cached, is_reverse_split # Data helpers
    from ai_handler import configure_gemini, get_batch_ai_validation # AI interaction
    from file_handler import save_to_csv # File saving
    # Import Discord notifier and history manager (assuming they exist)
    from discord_notifier import send_discord_notification
    from history_manager import load_notified_history, save_notified_history
except ImportError as e:
    # Provide a more helpful error message if a module is missing
    exit(f"ERROR: Failed to import necessary module: {e}. Ensure all required .py files (main.py, config.py, scraper.py, data_utils.py, ai_handler.py, file_handler.py, discord_notifier.py, history_manager.py) are present.")

# --- Main Execution Logic ---
if __name__ == "__main__":
    start_time = time.time()
    print(f"--- Starting Stock Split Checker ({datetime.datetime.now():%Y-%m-%d %H:%M:%S}) ---")

    # --- Initialize ---
    driver = None
    initial_records = [] # Store records after initial scraping and processing
    final_analyzed_data = [] # Store final results after merging AI analysis
    reverse_splits_to_analyze = [] # List to hold data specifically for the AI batch call
    # Load history at the start
    notified_keys_history = load_notified_history()

    # --- Configure AI ---
    ai_enabled = configure_gemini(secrets.GEMINI_API_KEY)

    try:
        # --- Setup WebDriver ---
        driver = setup_driver()
        if not driver:
            raise Exception("WebDriver initialization failed. Cannot proceed.")

        # --- Scrape Initial Split List ---
        headers, all_row_data_values = scrape_split_data(driver, secrets.URL)
        print(f"DEBUG: Scraped {len(all_row_data_values)} raw rows from website.") # <-- DEBUG PRINT 1
        if not all_row_data_values:
            print("No data scraped from the primary source. Exiting.")
            sys.exit()

        # --- Process Scraped Rows (Filter Dates, Get Exchange, Prepare for AI) ---
        print("\nProcessing scraped rows, filtering dates, getting Exchange...")
        today_date = datetime.date.today()
        required_indices = [config.TICKER_IDX, config.COMPANY_NAME_IDX, config.RATIO_IDX, config.EX_DATE_IDX];
        if config.EXCHANGE_IDX is not None: required_indices.append(config.EXCHANGE_IDX)
        MIN_EXPECTED_COLUMNS = max(required_indices) + 1 if required_indices else 1

        for i, row_values in enumerate(all_row_data_values):
            if not row_values or len(row_values) < MIN_EXPECTED_COLUMNS: continue
            try:
                ticker_val = row_values[config.TICKER_IDX]; company_val = row_values[config.COMPANY_NAME_IDX]
                ratio_val = row_values[config.RATIO_IDX]; ex_date_str = row_values[config.EX_DATE_IDX]
                exchange_val = row_values[config.EXCHANGE_IDX] if config.EXCHANGE_IDX is not None and config.EXCHANGE_IDX < len(row_values) else None
            except IndexError: continue

            if not ticker_val or not ratio_val or not ex_date_str or ex_date_str.upper() == 'N/A': continue

            ex_date_obj = None
            try: ex_date_obj = datetime.datetime.strptime(ex_date_str, '%Y-%m-%d').date()
            except ValueError: continue
            if ex_date_obj <= today_date: continue

            ex_date_cleaned = ex_date_obj.strftime('%Y-%m-%d')
            final_exchange = exchange_val if exchange_val else get_exchange_cached(ticker_val)

            record = {
                'Ticker': ticker_val, 'CompanyName': company_val, 'Ratio': ratio_val,
                'ExDate': ex_date_cleaned, 'Exchange': final_exchange,
                'fractional_share_handling': 'N/A (Forward Split)'
            }

            if is_reverse_split(ratio_val):
                record['fractional_share_handling'] = 'Pending AI Analysis'
                reverse_splits_to_analyze.append({
                    'ticker': ticker_val, 'ratio': ratio_val, 'ex_date': ex_date_cleaned
                })
            initial_records.append(record)

        print(f"DEBUG: Initial records count after filtering/processing: {len(initial_records)}") # <-- DEBUG PRINT 2
        print(f"DEBUG: Reverse splits identified for AI: {len(reverse_splits_to_analyze)}") # <-- DEBUG PRINT 3
        # if initial_records: print(f"DEBUG: Example initial record: {initial_records[0]}") # <-- DEBUG PRINT (Optional)

        # --- AI Call ---
        ai_results = {}
        if ai_enabled and reverse_splits_to_analyze:
            print(f"\nSending batch request to AI for {len(reverse_splits_to_analyze)} reverse splits...")
            ai_results = get_batch_ai_validation(reverse_splits_to_analyze)
            print(f"DEBUG: AI Results Dictionary received: {ai_results}") # <-- DEBUG PRINT 5
            print(f"AI analysis complete.")
        # ... (other AI status prints) ...

        # --- Merge AI Results ---
        print("\nMerging AI results into final data...")
        merged_count = 0
        for record in initial_records: # Iterate initial records
            if record['fractional_share_handling'] == 'Pending AI Analysis':
                ticker = record.get('Ticker')
                if ai_enabled:
                    classification = ai_results.get(ticker, 'AI Analysis Failed/Missing')
                    record['fractional_share_handling'] = classification
                    if ticker in ai_results and classification not in ["AI Response Missing", "AI API Error", "AI Response Unclear", "AI Analysis Failed/Missing"]:
                        merged_count +=1
                else:
                     record['fractional_share_handling'] = "AI Disabled"
            final_analyzed_data.append(record) # Append processed record to final list

        if ai_enabled and reverse_splits_to_analyze:
            print(f"Merged AI results for {merged_count} tickers (excluding errors/missing/unclear).")
        print(f"DEBUG: Final records count before saving/notification: {len(final_analyzed_data)}") # <-- DEBUG PRINT 6
        # if final_analyzed_data: print(f"DEBUG: Example final record: {final_analyzed_data[0]}") # <-- DEBUG PRINT (Optional)

        # --- Save Final Analyzed Data to CSV ---
        if final_analyzed_data:
            print(f"DEBUG: Attempting to save {len(final_analyzed_data)} records to CSV...") # <-- DEBUG PRINT 8
            save_to_csv(final_analyzed_data) # Uses FINAL_CSV_FILE_PATH from config
        else:
            print("No final data to save to CSV.")

        # --- Discord Notifications ---
        notifications_sent_this_run = 0
        notifications_skipped_history = 0
        notifications_failed_this_run = 0
        # Work with a copy of the loaded history; update main history only if sends succeed
        current_run_notified_keys = notified_keys_history.copy()

        # --- DEBUG PRINTS for Discord Conditions ---
        print(f"\nDEBUG: Checking conditions for Discord notifications.")
        print(f"DEBUG: final_analyzed_data has {len(final_analyzed_data)} items.")
        # Be careful printing secrets, maybe just check if it's None or not
        webhook_is_set = bool(secrets.DISCORD_WEBHOOK_URL)
        print(f"DEBUG: DISCORD_WEBHOOK_URL is set: {webhook_is_set}")
        # print(f"DEBUG: DISCORD_WEBHOOK_URL is set to: {secrets.DISCORD_WEBHOOK_URL}") # <-- Uncomment cautiously if needed

        if final_analyzed_data and secrets.DISCORD_WEBHOOK_URL:
            print(f"\nDEBUG: Conditions met. Entering notification loop...") # <-- DEBUG PRINT
            for record in final_analyzed_data:
                ticker_key = record.get('Ticker', 'UNKNOWN'); ex_date_key = record.get('ExDate', 'NODATE')
                notification_key = f"{ticker_key}_{ex_date_key}"

                # Check history
                if notification_key in notified_keys_history:
                    print(f"  DEBUG: Skipping notification for {notification_key}: Found in history.") # <-- DEBUG PRINT
                    notifications_skipped_history += 1; continue

                # Attempt to send notification
                print(f"  Attempting notification for new split: {notification_key}") # Check if this prints
                success = send_discord_notification(secrets.DISCORD_WEBHOOK_URL, record) # Store return value
                print(f"  DEBUG: send_discord_notification returned: {success}") # <-- DEBUG PRINT (Check True/False)
                if success:
                     notifications_sent_this_run += 1; current_run_notified_keys.add(notification_key) # Add to set on success
                else:
                     notifications_failed_this_run += 1
                # Use delay from config
                time.sleep(config.DISCORD_RATE_LIMIT_DELAY)

            print("\nFinished Discord notifications loop.")
            print(f"  New Sent: {notifications_sent_this_run}, Skipped: {notifications_skipped_history}, Failed: {notifications_failed_this_run}")
            # Update the main history set with keys successfully notified this run
            notified_keys_history = current_run_notified_keys

        elif not secrets.DISCORD_WEBHOOK_URL:
            print("\nSkipping Discord: Webhook URL not configured in main.py.")
        else: # final_analyzed_data is empty
            print("\nSkipping Discord: No final data available to send.") # <-- This might be the reason


    # --- General Error Handling ---
    except KeyboardInterrupt: print("\nScript interrupted by user.")
    except Exception as e:
        print(f"\nFATAL ERROR in main execution: {type(e).__name__} - {e}")
        import traceback; traceback.print_exc()

    # --- Cleanup Actions ---
    finally:
        if driver:
            print("\nClosing WebDriver...")
            try: driver.quit()
            except Exception as quit_err: print(f"Warning: Error closing WebDriver: {quit_err}")
            print("WebDriver closed.")

        # --- Save History ---
        # Ensure history is saved even if errors occurred mid-process
        save_notified_history(notified_keys_history) # Uses path from config

        # --- Timing ---
        end_time = time.time()
        print(f"\n--- Script Finished ({datetime.datetime.now():%Y-%m-%d %H:%M:%S}) ---")
        print(f"--- Total Execution Time: {end_time - start_time:.2f} seconds ---")