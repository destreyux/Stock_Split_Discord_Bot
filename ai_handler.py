# ai_handler.py
"""Handles interaction with the Gemini API using batch questions."""

import google.generativeai as genai
import datetime
import json
import os
import config # Import constants
import traceback # <--- Added for detailed error printing

# Store API Key globally within this module after configuration
_GEMINI_API_KEY_CONFIGURED = None

def configure_gemini(api_key):
    """Configures the Gemini API if a key is provided."""
    global _GEMINI_API_KEY_CONFIGURED
    if api_key:
        try:
            genai.configure(api_key=api_key)
            _GEMINI_API_KEY_CONFIGURED = api_key
            print(f"Gemini API configured for {config.AI_MODEL_NAME}.")
            return True
        except Exception as e:
            print(f"Warning: Error configuring Gemini API: {e}. AI validation skipped.")
            _GEMINI_API_KEY_CONFIGURED = None
            return False
    else:
        print("No Gemini API Key provided. AI validation will be skipped.")
        _GEMINI_API_KEY_CONFIGURED = None
        return False

# --- Log function signature matches batch request ---
def log_ai_response(log_filepath, timestamp, tickers_requested, raw_response_text):
    """Appends AI call log entry to a JSON Lines file."""
    log_entry = {
        "timestamp": timestamp, "model_used": config.AI_MODEL_NAME,
        "tickers_requested": tickers_requested, # Log the list of tickers
        "raw_response_text": raw_response_text
    }
    try:
        dir_name = os.path.dirname(log_filepath);
        if dir_name: os.makedirs(dir_name, exist_ok=True)
        with open(log_filepath, 'a', encoding='utf-8') as f:
            json.dump(log_entry, f, ensure_ascii=False); f.write('\n')
    except Exception as e: print(f"Warning: Could not write AI log: {e}")


# --- REVERTED get_batch_ai_validation FOR SIMPLE QUESTION PROMPT (BATCH) ---
def get_batch_ai_validation(reverse_split_list):
    """
    Sends batch request to Gemini API using a simple question format for each split.
    Returns classification {ticker: classification_string}. Logs raw response.
    Includes detailed error printing on API failure.
    """
    if not _GEMINI_API_KEY_CONFIGURED: return {}
    if not reverse_split_list: return {}
    model = genai.GenerativeModel(config.AI_MODEL_NAME)

    # --- Define the EXACT classification phrases from config ---
    CLASSIFICATION_PHRASES = config.CLASSIFICATION_PHRASES
    OUTPUT_ROUND_UP = config.OUTPUT_ROUND_UP
    OUTPUT_CASH = config.OUTPUT_CASH
    OUTPUT_UNKNOWN = config.OUTPUT_UNKNOWN

    # --- Simple Prompt Header - Focuses on OUTPUT FORMAT ---
    prompt_header = f"""
ANSWER THE FOLLOWING QUESTIONS:
How will [Ticker] reverse split fractional shares be handled?,
How will [Companyname] reverse split fractional shares be handled?

ONLY ANSWER IN THE FOLLOWING CONCLUSION:
[Ticker]: Rounding Up Likely
[Ticker]: Cash-in-Lieu Likely

**Questions:**
"""

    prompt_body = ""
    tickers_sent_map = {} # Map line number to ticker for accurate tracking
    line_num = 1
    for split_info in reverse_split_list:
        ticker = split_info.get('ticker', 'N/A')
        ex_date_str = split_info.get('ex_date', 'N/A')
        # Format the simple question
        # Added ratio for slightly more context for the AI
        ratio_str = split_info.get('ratio', 'N/A')
        prompt_body += f"{line_num}. Is {ticker}'s {ratio_str} reverse split fractional shares going to round up or be cash-in-lieu? (Ex-Date approx {ex_date_str})\n"
        tickers_sent_map[line_num] = ticker # Store ticker associated with line number
        line_num += 1

    full_prompt = prompt_header + prompt_body.strip()
    # Get the list of unique tickers sent in this batch for logging/error handling
    tickers_sent_list = list(dict.fromkeys([info['ticker'] for info in reverse_split_list if 'ticker' in info]))

    print(f"Sending batch request (Simple Question Format) to Gemini for {len(tickers_sent_list)} unique tickers...")
    # Map will store {ticker: classification_string}
    ai_results_map = {}
    response_text = ""
    log_timestamp = datetime.datetime.now().isoformat()

    try:
        generation_config = {'temperature': config.AI_REQUEST_TEMPERATURE} # Use temp from config
        response = model.generate_content(full_prompt, generation_config=generation_config)
        response_text = response.text
        print(f"  Received response from Gemini. Logging raw text...")
        # Log using the list of unique tickers sent
        log_ai_response(config.AI_LOG_FILE_PATH, log_timestamp, tickers_sent_list, response_text)

    # --- MODIFIED EXCEPTION BLOCK ---
    except Exception as e:
        print(f"\n---!!! Gemini API Error Encountered !!!---")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")
        print("--- Full Traceback ---")
        traceback.print_exc() # Print the detailed traceback
        print("--- End Traceback ---")
        # Return simple error map using the list of unique tickers
        return {t: "AI API Error" for t in tickers_sent_list}
    # --- END MODIFIED EXCEPTION BLOCK ---

    # --- Parsing Logic (Expects only Ticker: Classification) ---
    print("Parsing AI response...")
    response_lines = response_text.splitlines()
    allowed_results_lower = { phrase.lower() for phrase in CLASSIFICATION_PHRASES }
    result_map_lower_to_proper = { phrase.lower(): phrase for phrase in CLASSIFICATION_PHRASES }

    # Initialize results map with defaults for all requested unique tickers
    for ticker in tickers_sent_list:
         ai_results_map[ticker] = "AI Response Missing" # Default

    processed_tickers = set() # Track tickers we found a response for
    for line in response_lines:
        line = line.strip()
        if not line: continue
        # Handle potential numbering like "1. Ticker: Result"
        if '.' in line:
            potential_num = line.split('.', 1)[0]
            if potential_num.isdigit():
                 # It looks like a numbered list item, remove number and dot
                 line = line.split('.', 1)[1].strip()

        parts = line.split(":", 1)
        if len(parts) == 2:
            ticker_from_ai, result_from_ai = parts[0].strip(), parts[1].strip()
            result_lower = result_from_ai.lower()

            # Check if this ticker was actually requested AND hasn't been processed yet
            if ticker_from_ai in tickers_sent_list and ticker_from_ai not in processed_tickers:
                if result_lower in allowed_results_lower:
                    ai_results_map[ticker_from_ai] = result_map_lower_to_proper[result_lower]
                else:
                    # Didn't match expected phrases exactly
                    print(f"Warning: Unexpected AI result format for {ticker_from_ai}: '{result_from_ai}'")
                    ai_results_map[ticker_from_ai] = "AI Response Unclear"
                processed_tickers.add(ticker_from_ai) # Mark as processed
            # else: Ignore unexpected/repeated tickers

    # Final check for any tickers requested but not found in the response
    missing_tickers = set(tickers_sent_list) - processed_tickers
    if missing_tickers:
         print(f"Warning: AI response still missing for expected tickers: {missing_tickers}")
         # The map already has "AI Response Missing" as default for these

    print(f"Finished parsing AI classification. Results obtained for {len(processed_tickers)}/{len(tickers_sent_list)} tickers.")
    return ai_results_map # Returns {ticker: classification_string}