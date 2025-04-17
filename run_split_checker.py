# run_split_checker.py
"""
Main script:
1. Scrapes upcoming splits.
2. Enriches with exchange info.
3. Sends batch request to AI for reverse split fractional analysis.
4. Merges AI results.
5. Saves final analyzed data to CSV.
"""
import pandas as pd
import datetime
import time
import os
import sys

# --- Import configuration and modules ---
try:
    import main as secrets
    import config
    from scraper import setup_driver, scrape_split_data
    from data_utils import get_exchange_cached, is_reverse_split
    from ai_handler import configure_gemini, get_batch_ai_validation
    from file_handler import save_to_csv
except ImportError as e:
    exit(f"ERROR: Failed to import necessary module: {e}. Ensure all required .py files are present.")

# --- Main Execution Logic ---
if __name__ == "__main__":
    start_time = time.time()
    print(f"--- Starting Stock Split Checker ({datetime.datetime.now():%Y-%m-%d %H:%M:%S}) ---")

    driver = None
    initial_records = []
    final_analyzed_data = []
    reverse_splits_to_analyze = []
    ai_enabled = configure_gemini(secrets.GEMINI_API_KEY)

    try:
        driver = setup_driver()
        if not driver: raise Exception("WebDriver initialization failed.")

        headers, all_row_data_values = scrape_split_data(driver, secrets.URL)
        print(f"DEBUG: Scraped {len(all_row_data_values)} raw rows from website.") # <-- DEBUG PRINT 1
        if not all_row_data_values:
            print("No data scraped from the primary source. Exiting.")
            sys.exit()

        print("\nProcessing scraped rows, filtering dates, getting Exchange...")
        today_date = datetime.date.today()
        required_indices = [config.TICKER_IDX, config.COMPANY_NAME_IDX, config.RATIO_IDX, config.EX_DATE_IDX];
        if config.EXCHANGE_IDX is not None: required_indices.append(config.EXCHANGE_IDX)
        MIN_EXPECTED_COLUMNS = max(required_indices) + 1 if required_indices else 1

        for i, row_values in enumerate(all_row_data_values):
            # ... (row validation and data extraction) ...
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
            # --- If row passes all checks up to here, process it ---
            ex_date_cleaned = ex_date_obj.strftime('%Y-%m-%d')
            final_exchange = exchange_val if exchange_val else get_exchange_cached(ticker_val)
            record = { # Build the record
                'Ticker': ticker_val, 'CompanyName': company_val, 'Ratio': ratio_val,
                'ExDate': ex_date_cleaned, 'Exchange': final_exchange,
                'fractional_share_handling': 'N/A (Forward Split)'
            }
            if is_reverse_split(ratio_val):
                record['fractional_share_handling'] = 'Pending AI Analysis'
                reverse_splits_to_analyze.append({
                    'ticker': ticker_val, 'ratio': ratio_val, 'ex_date': ex_date_cleaned
                })
            initial_records.append(record) # Add the processed record

        print(f"DEBUG: Initial records count after filtering/processing: {len(initial_records)}") # <-- DEBUG PRINT 2
        print(f"DEBUG: Reverse splits identified for AI: {len(reverse_splits_to_analyze)}") # <-- DEBUG PRINT 3
        if initial_records: print(f"DEBUG: Example initial record: {initial_records[0]}") # <-- DEBUG PRINT 4 (Example Record)

        # --- AI Call ---
        ai_results = {}
        if ai_enabled and reverse_splits_to_analyze:
            print(f"\nSending batch request to AI for {len(reverse_splits_to_analyze)} reverse splits...")
            ai_results = get_batch_ai_validation(reverse_splits_to_analyze)
            print(f"DEBUG: AI Results Dictionary received: {ai_results}") # <-- DEBUG PRINT 5 (See AI Output Dict)
            print(f"AI analysis complete.")
        # ... (other AI status prints) ...

        # --- Merge AI Results ---
        print("\nMerging AI results into final data...")
        merged_count = 0
        for record in initial_records: # Iterate initial records
            # print(f"DEBUG: Processing record for merge: {record}") # <-- DEBUG PRINT (Optional, can be verbose)
            if record['fractional_share_handling'] == 'Pending AI Analysis':
                ticker = record.get('Ticker')
                if ai_enabled:
                    classification = ai_results.get(ticker, 'AI Analysis Failed/Missing')
                    # print(f"DEBUG: Merging for {ticker}. Found AI result: {classification}") # <-- DEBUG PRINT (Optional)
                    record['fractional_share_handling'] = classification
                    if ticker in ai_results and classification not in ["AI Response Missing", "AI API Error", "AI Response Unclear", "AI Analysis Failed/Missing"]:
                        merged_count +=1
                else:
                     record['fractional_share_handling'] = "AI Disabled"
            final_analyzed_data.append(record) # Append processed record to final list

        if ai_enabled and reverse_splits_to_analyze:
            print(f"Merged AI results for {merged_count} tickers (excluding errors/missing/unclear).")
        print(f"DEBUG: Final records count before saving: {len(final_analyzed_data)}") # <-- DEBUG PRINT 6
        if final_analyzed_data: print(f"DEBUG: Example final record: {final_analyzed_data[0]}") # <-- DEBUG PRINT 7 (Example Record)


        # --- Save Final Analyzed Data to CSV ---
        if final_analyzed_data:
            print(f"DEBUG: Attempting to save {len(final_analyzed_data)} records to CSV...") # <-- DEBUG PRINT 8
            save_to_csv(final_analyzed_data)
        else:
            print("No final data to save to CSV.")


    except KeyboardInterrupt: print("\nScript interrupted by user.")
    except Exception as e:
        print(f"\nFATAL ERROR in main execution: {type(e).__name__} - {e}")
        import traceback; traceback.print_exc()
    finally:
        if driver:
            print("\nClosing WebDriver...")
            try: driver.quit()
            except Exception as quit_err: print(f"Warning: Error closing WebDriver: {quit_err}")
            print("WebDriver closed.")
        # ... (optional history save) ...
        end_time = time.time()
        print(f"\n--- Script Finished ({datetime.datetime.now():%Y-%m-%d %H:%M:%S}) ---")
        print(f"--- Total Execution Time: {end_time - start_time:.2f} seconds ---")