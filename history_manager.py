# history_manager.py
"""Manages loading and saving the notification history."""

import os
import config # Import constants

def load_notified_history(filepath=config.HISTORY_FILE_PATH):
    """Loads previously notified split keys (Ticker_ExDate) from a file."""
    notified = set()
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    key = line.strip()
                    if key: notified.add(key)
            print(f"Loaded {len(notified)} entries from notification history '{filepath}'.")
        else:
            print(f"Notification history file '{filepath}' not found. Starting fresh.")
    except Exception as e:
        print(f"Warning: Could not load notification history from {filepath}: {e}")
    return notified

def save_notified_history(notified_set, filepath=config.HISTORY_FILE_PATH):
    """Saves the updated set of notified split keys to a file."""
    print(f"Attempting to save {len(notified_set)} entries to notification history '{filepath}'...")
    try:
        dir_name = os.path.dirname(filepath)
        if dir_name: os.makedirs(dir_name, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            # Save sorted list for better readability and diffing
            for key in sorted(list(notified_set)):
                f.write(key + '\n')
        print(f"Successfully saved notification history to {filepath}")
    except Exception as e:
        print(f"Error: Could not save notification history to {filepath}: {e}")