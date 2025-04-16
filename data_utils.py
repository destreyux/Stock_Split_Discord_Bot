# data_utils.py
"""Utility functions for data validation and external lookups."""

import yfinance as yf
import requests
import time
import os

# Cache for yfinance lookups within a single run
exchange_cache = {}

def get_exchange_cached(ticker):
    """Fetches stock exchange from yfinance, using a simple cache."""
    if ticker in exchange_cache:
        return exchange_cache[ticker]

    print(f"  Looking up exchange for {ticker} via yfinance...")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        exchange = info.get('exchange')
        if exchange:
            exchange_map = { "NMS": "NASDAQ", "NYQ": "NYSE", "ASE": "NYSE AMEX", "PNK": "OTC Pink", "OQB": "OTCQB", "OTCQX": "OTCQX", "TOR": "TSX", "VAN": "TSX-V" }
            mapped_exchange = exchange_map.get(exchange, exchange)
            print(f"    -> Found exchange: {mapped_exchange}")
            exchange_cache[ticker] = mapped_exchange
            return mapped_exchange
        else:
            quote_type = info.get('quoteType')
            if quote_type == 'ETF' and info.get('market') and 'us_market' in info.get('market'):
                 print(f"    -> Found ETF market (assumed US): {info.get('market')}")
                 exchange_cache[ticker] = "US ETF Market"
                 return "US ETF Market"
            print(f"    -> Exchange info not found for {ticker} in yfinance data.")
            exchange_cache[ticker] = 'N/A'
            return 'N/A'
    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 404: print(f"    -> Ticker {ticker} not found on Yahoo Finance (404 Error).")
        else: print(f"    -> HTTP error looking up {ticker}: {http_err}")
        exchange_cache[ticker] = 'Lookup Failed (HTTP)'
        return 'Lookup Failed (HTTP)'
    except Exception as e:
        print(f"    -> Error looking up exchange for {ticker}: {type(e).__name__}")
        exchange_cache[ticker] = 'Lookup Failed'
        return 'Lookup Failed'
    time.sleep(0.2) # Small delay between lookups


def is_reverse_split(ratio_str):
    """Checks if a ratio string represents a reverse split."""
    try:
        if not isinstance(ratio_str, str) or not ratio_str: return False
        ratio_str = ratio_str.strip()
        parts = []
        if ':' in ratio_str: parts = ratio_str.split(':')
        elif '/' in ratio_str: parts = ratio_str.split('/')
        elif '-for-' in ratio_str.lower(): parts = ratio_str.lower().split('-for-')
        else: return False
        if len(parts) != 2: return False
        part1 = float(parts[0].strip())
        part2 = float(parts[1].strip())
        return part1 < part2
    except (ValueError, IndexError, TypeError):
        return False