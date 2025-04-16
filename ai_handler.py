# ai_handler.py
"""Handles interaction with the Gemini API and logs responses."""

import google.generativeai as genai
import datetime
import json
import os
import config # Import constants

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

def log_ai_response(log_filepath, timestamp, tickers_requested, raw_response_text):
    """Appends a log entry for an AI API call to a JSON Lines file."""
    log_entry = {
        "timestamp": timestamp,
        "model_used": config.AI_MODEL_NAME,
        "tickers_requested": tickers_requested,
        "raw_response_text": raw_response_text
    }
    try:
        dir_name = os.path.dirname(log_filepath)
        if dir_name: os.makedirs(dir_name, exist_ok=True)
        with open(log_filepath, 'a', encoding='utf-8') as f:
            json.dump(log_entry, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        print(f"Warning: Could not write AI response to log file '{log_filepath}': {e}")


def get_batch_ai_validation(reverse_split_list):
    """
    Sends batch request to Gemini API, asking for reasoning, logs raw response.
    Returns a dictionary mapping tickers to {'result': ..., 'reasoning': ...}.
    """
    if not _GEMINI_API_KEY_CONFIGURED: return {} # Check if API was configured
    if not reverse_split_list: return {}
    model = genai.GenerativeModel(config.AI_MODEL_NAME)

    # Use constants from config
    CLASSIFICATION_PHRASES = config.CLASSIFICATION_PHRASES
    OUTPUT_ROUND_UP = config.OUTPUT_ROUND_UP
    OUTPUT_CASH = config.OUTPUT_CASH
    OUTPUT_UNKNOWN = config.OUTPUT_UNKNOWN

    # --- PROMPT ASKING FOR REASONING ---
    # (Using the last version you provided - emphasizing Google search, lenient sources)
    prompt_header = f"""
Analyze the likely handling of fractional shares for the following REVERSE stock splits based on their Ticker, Ratio, and Ex-Date.

**Primary Search Method:**
*   Perform a search equivalent to using Google with the query: `[TICKER] reverse split fractional shares`.
*   Analyze top results, considering sources like SEC filings, exchange notices, reputable news (stocktitan.net, Reuters, Bloomberg), broker docs for THIS split.

**Determine the LIKELY handling:**
- {OUTPUT_ROUND_UP}: If evidence suggests rounding up.
- {OUTPUT_CASH}: If evidence suggests cash OR lack of round-up specifics (default).
- {OUTPUT_UNKNOWN}: If sources conflict significantly or info is scarce.

**Response Format:**
For each ticker, respond on a new line with:
`Ticker: Classification | Reasoning: [Brief explanation of the key evidence/source found]`

**Example:**
XYZ: {OUTPUT_CASH} | Reasoning: No mention of rounding up found in recent 8-K filing or news searches, implying default cash handling.
ABC: {OUTPUT_ROUND_UP} | Reasoning: Company press release dated [Date] explicitly stated fractions will be rounded up to the nearest whole share.
SUNE: {OUTPUT_ROUND_UP} | Reasoning: Stocktitan and recent press release confirm round-up election for the May 2024 split.
GHI: {OUTPUT_UNKNOWN} | Reasoning: Conflicting information found between broker FAQ and a news report; official filing unclear on fractional handling.

**Reverse splits to analyze:**
"""

    prompt_body = ""
    tickers_sent = []
    for i, split_info in enumerate(reverse_split_list):
        ticker = split_info.get('ticker', 'N/A')
        ratio = split_info.get('ratio', 'N/A')
        ex_date_str = split_info.get('ex_date', 'N/A')
        year = ex_date_str.split('-')[0] if ex_date_str and '-' in ex_date_str else "recent"
        prompt_body += f"{i+1}. {ticker} (Ratio: {ratio}, Ex-Date: {ex_date_str}, Year: {year})\n"
        tickers_sent.append(ticker)

    full_prompt = prompt_header + prompt_body.strip()

    print(f"Sending batch request w/ REASONING to Gemini for {len(reverse_split_list)} splits...")
    ai_results_map = {}
    response_text = ""
    log_timestamp = datetime.datetime.now().isoformat()

    try:
        generation_config = {'temperature': 0.3}
        response = model.generate_content(full_prompt, generation_config=generation_config)
        response_text = response.text
        print(f"  Received response from Gemini. Logging raw text...")
        log_ai_response(config.AI_LOG_FILE_PATH, log_timestamp, tickers_sent, response_text)
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return {t: {'result': "AI API Error", 'reasoning': ''} for t in tickers_sent}

    # --- Attempt to Parse Classification AND Reasoning ---
    print("Parsing AI response (including reasoning attempt)...")
    response_lines = response_text.splitlines()
    for ticker in tickers_sent:
         ai_results_map[ticker] = {'result': "AI Response Missing", 'reasoning': ''}

    for line in response_lines:
        line = line.strip();
        if not line: continue
        parts = line.split(":", 1);
        if len(parts) < 2: continue
        ticker_from_ai, rest_of_line = parts[0].strip(), parts[1].strip()
        if ticker_from_ai not in tickers_sent: continue

        parsed_result = "AI Response Unclear"; extracted_reasoning = rest_of_line
        found_classification = False
        for phrase in CLASSIFICATION_PHRASES:
            if rest_of_line.startswith(phrase):
                parsed_result = phrase; found_classification = True
                potential_reasoning = rest_of_line[len(phrase):].strip()
                if potential_reasoning.startswith("| Reasoning:"): extracted_reasoning = potential_reasoning[len("| Reasoning:"):].strip()
                elif potential_reasoning.startswith("|"): extracted_reasoning = potential_reasoning[1:].strip()
                elif potential_reasoning.startswith("Reasoning:"): extracted_reasoning = potential_reasoning[len("Reasoning:"):].strip()
                elif potential_reasoning.startswith("-"): extracted_reasoning = potential_reasoning[1:].strip()
                elif potential_reasoning: extracted_reasoning = potential_reasoning
                else: extracted_reasoning = "(Reasoning not distinctly separated or provided)"
                break

        if not found_classification: # Fallback check if phrase is just contained
             for phrase in CLASSIFICATION_PHRASES:
                  if phrase in rest_of_line:
                       print(f"Warning: Found classification '{phrase}' for {ticker_from_ai}, but not at start. Parsing might be inaccurate.")
                       reasoning_parts = rest_of_line.split(phrase, 1)
                       parsed_result = phrase
                       extracted_reasoning = reasoning_parts[1].strip() if len(reasoning_parts) > 1 else "(Fallback Parse - Reasoning unclear)"
                       break

        ai_results_map[ticker_from_ai] = {'result': parsed_result, 'reasoning': extracted_reasoning}

    print(f"Finished parsing AI response attempt. Results obtained for {len(ai_results_map)}/{len(tickers_sent)} tickers.")
    return ai_results_map