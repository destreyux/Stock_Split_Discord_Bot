# discord_notifier.py
"""Handles sending notifications to Discord."""

import requests
import datetime
import time
import config # Import constants

def send_discord_notification(webhook_url, split_data):
    """Sends an embed message to Discord, including the Exchange."""
    if not webhook_url: return False
    headers = {"Content-Type": "application/json"}
    fields = [
        {"name": "Ticker", "value": split_data.get('Ticker', 'N/A'), "inline": True},
        {"name": "Exchange", "value": split_data.get('Exchange', 'N/A'), "inline": True},
        {"name": "Ratio", "value": split_data.get('Ratio', 'N/A'), "inline": True},
        {"name": "Company", "value": split_data.get('CompanyName', 'N/A'), "inline": False},
        {"name": "Buy Before (Ex-Date)", "value": split_data.get('ExDate', 'N/A'), "inline": True},
        {"name": "Fractional Handling", "value": split_data.get('fractional_share_handling', 'N/A'), "inline": True}
        # Optionally add AI Reasoning field here if desired, maybe truncated
        # {"name": "AI Reasoning", "value": split_data.get('ai_reasoning', 'N/A')[:1000], "inline": False}
    ]
    payload = {
        "embeds": [{
            "title": "📈 Upcoming Stock Split Alert",
            "color": 3447003, # Discord Blue
            "fields": fields,
            "footer": {"text": "Source: Automated Stock Split Script"},
            "timestamp": datetime.datetime.utcnow().isoformat()
        }]
    }
    try:
        response = requests.post(webhook_url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        print(f"  Successfully sent Discord notification for {split_data.get('Ticker', 'N/A')}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord notification for {split_data.get('Ticker', 'N/A')}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during Discord notification for {split_data.get('Ticker', 'N/A')}: {e}")
        return False