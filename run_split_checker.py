# run_split_checker.py
"""Main script to orchestrate the stock split checking process."""

import pandas as pd
import datetime
import time
import os
import sys

# --- Import configuration and modules ---
try:
    import main as secrets # Keep secrets separate
    import config # General settings
    from scraper import setup_driver, scrape_split_data
    from data_utils import get_exchange_cached, is_reverse_split
    from ai_handler import configure_gemini, get_batch_ai_validation
    from discord_notifier import send_discord_notification
    from history_manager import load_notified_history, save_notified_history
except ImportError as e:
    exit(f"ERROR: Failed to import necessary module: {e}. Ensure all .py files are present.")

# --- Main Execution Logic ---
if __name__ == "__main__":
    start_time = time.time()
    print(f"--- Starting Stock Split Checker ({datetime.datetime.now():%Y-%m-%d %H:%M:%S}) ---")

    # --- Initialize ---
    driver = None
    initial_records = []
    reverse_splits_to_analyze = []
    final_scraped_data = []
    processed_count_final = 0
    notified_keys_history = load_notified_history() # Uses path from config

    # --- Configure AI ---
    ai_enabled = configure_gemini(secrets.GEMINI_API_KEY)

    try:
        # --- Setup WebDriver ---
        driver = setup_driver()
        if not driver:
             raise Exception("WebDriver initialization failed.") # Stop if driver fails

        # --- Scrape Data ---
        headers, all_row_data_values = scrape_split_data(driver, secrets.URL)
        if not all_row_data_values:
            print("No data scraped from the website. Exiting.")
            sys.exit() # Use sys.exit for cleaner exit

        # --- First Pass: Processing, Filtering, Exchange Lookup ---
        print("\nFirst pass: Processing rows, filtering dates, getting Exchange...")
        today_date = datetime.date.today()
        first_pass_processed_count = 0
        required_indices = [config.TICKER_IDX, config.COMPANY_NAME_IDX, config.RATIO_IDX, config.EX_DATE_IDX];
        if config.EXCHANGE_IDX is not None: required_indices.append(config.EXCHANGE_IDX)
        MIN_EXPECTED_COLUMNS = max(required_indices) + 1 if required_indices else 1

        for i, row_values in enumerate(all_row_data_values):
            first_pass_processed_count += 1
            if not row_values or len(row_values) < MIN_EXPECTED_COLUMNS: continue

            try:
                ticker_val = row_values[config.TICKER_IDX]
                company_val = row_values[config.COMPANY_NAME_IDX]
                ratio_val = row_values[config.RATIO_IDX]
                ex_date_str = row_values[config.EX_DATE_IDX]
                exchange_val = row_values[config.EXCHANGE_IDX] if config.EXCHANGE_IDX is not None and config.EXCHANGE_IDX < len(row_values) else None
            except IndexError: print(f"Warning: Skipping row {i+1} due to IndexError."); continue

            if not ticker_val or not ratio_val or not ex_date_str or ex_date_str.upper() == 'N/A': continue

            ex_date_obj = None
            try: ex_date_obj = datetime.datetime.strptime(ex_date_str, '%Y-%m-%d').date()
            except ValueError: print(f"Warning: Invalid date '{ex_date_str}' for {ticker_val}. Skipping."); continue
            if ex_date_obj <= today_date: continue

            ex_date_cleaned = ex_date_obj.strftime('%Y-%m-%d')
            final_exchange = exchange_val if exchange_val else get_exchange_cached(ticker_val)

            record = {
                'Ticker': ticker_val, 'CompanyName': company_val, 'Ratio': ratio_val,
                'ExDate': ex_date_cleaned, 'Exchange': final_exchange,
                'fractional_share_handling': 'N/A (Forward Split or Pending AI)'
            }

            if is_reverse_split(ratio_val):
                record['fractional_share_handling'] = 'Pending AI Analysis'
                reverse_splits_to_analyze.append({ 'ticker': ticker_val, 'ratio': ratio_val, 'ex_date': ex_date_cleaned })

            initial_records.append(record)

        print(f"Finished first pass. Processed {first_pass_processed_count} raw rows.")
        print(f"Identified {len(initial_records)} splits with future Ex-Dates.")

        # --- AI Call ---
        ai_results = {} # Stores dict: {ticker: {'result': '...', 'reasoning': '...'}}
        if ai_enabled and reverse_splits_to_analyze:
            print(f"\nFound {len(reverse_splits_to_analyze)} reverse splits needing AI analysis.")
            ai_results = get_batch_ai_validation(reverse_splits_to_analyze)
            print(f"AI analysis complete.")
        elif not ai_enabled and reverse_splits_to_analyze:
             print("\nAI is disabled. Skipping fractional share analysis.")
        else:
            print("\nNo reverse splits needing AI analysis.")

        # --- Second Pass: Merge AI Results ---
        print("\nSecond pass: Merging AI results...")
        for record in initial_records:
            ticker = record['Ticker']
            if record['fractional_share_handling'] == 'Pending AI Analysis':
                if ai_enabled:
                    ai_info = ai_results.get(ticker, {}) # Get the dict for the ticker
                    record['fractional_share_handling'] = ai_info.get('result', 'AI Analysis Failed/Missing') # Get the 'result'
                else:
                     record['fractional_share_handling'] = "AI Disabled" # Mark as disabled if AI wasn't run
            final_scraped_data.append(record)
            processed_count_final += 1
        print(f"Finished merging. Prepared {processed_count_final} final records.")

        # --- Save to CSV ---
        if final_scraped_data:
            try:
                df = pd.DataFrame(final_scraped_data)
                df['scrape_timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                desired_cols = ['scrape_timestamp', 'Ticker', 'Exchange', 'CompanyName', 'Ratio', 'ExDate', 'fractional_share_handling']
                final_cols = [col for col in desired_cols if col in df.columns]
                extra_cols = [col for col in df.columns if col not in final_cols]
                df = df[final_cols + extra_cols]
                df.to_csv(config.CSV_FILE_PATH, index=False, encoding='utf-8')
                print(f"\nSuccessfully saved {processed_count_final} records to '{config.CSV_FILE_PATH}'")
            except Exception as csv_err: print(f"\nError saving to CSV '{config.CSV_FILE_PATH}': {csv_err}")
        else: print(f"\nNo records to save. CSV not updated.")

        # --- Discord Notifications ---
        notifications_sent_this_run = 0; notifications_skipped_history = 0; notifications_failed_this_run = 0
        current_run_notified_keys = notified_keys_history.copy()

        if final_scraped_data and secrets.DISCORD_WEBHOOK_URL:
            print(f"\nChecking {len(final_scraped_data)} potential notifications...")
            for record in final_scraped_data:
                ticker_key = record.get('Ticker', 'UNKNOWN'); ex_date_key = record.get('ExDate', 'NODATE')
                notification_key = f"{ticker_key}_{ex_date_key}"

                if notification_key in notified_keys_history:
                    notifications_skipped_history += 1; continue

                print(f"  Attempting notification for new split: {notification_key}")
                if send_discord_notification(secrets.DISCORD_WEBHOOK_URL, record):
                     notifications_sent_this_run += 1; current_run_notified_keys.add(notification_key)
                else: notifications_failed_this_run += 1
                time.sleep(config.DISCORD_RATE_LIMIT_DELAY) # Use delay from config

            print("\nFinished Discord notifications.")
            print(f"  New Sent: {notifications_sent_this_run}, Skipped: {notifications_skipped_history}, Failed: {notifications_failed_this_run}")
            notified_keys_history = current_run_notified_keys # Update main history set
        elif not secrets.DISCORD_WEBHOOK_URL: print("\nSkipping Discord: Webhook URL not configured.")
        else: print("\nSkipping Discord: No new data.")

    # --- Error Handling for main execution ---
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    except Exception as e:
        print(f"\nFATAL ERROR in main execution: {type(e).__name__} - {e}")
        import traceback; traceback.print_exc()
    finally:
        # --- Cleanup ---
        if driver:
            print("\nClosing WebDriver...")
            try: driver.quit()
            except Exception as quit_err: print(f"Warning: Error closing WebDriver: {quit_err}")
            print("WebDriver closed.")

        # --- Save History ---
        # Ensure history is saved even if errors occurred mid-process
        save_notified_history(notified_keys_history) # Uses path from config

        end_time = time.time()
        print(f"\n--- Script Finished ({datetime.datetime.now():%Y-%m-%d %H:%M:%S}) ---")
        print(f"--- Total Execution Time: {end_time - start_time:.2f} seconds ---")