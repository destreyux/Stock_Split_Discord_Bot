# scraper.py
"""Handles the Selenium web scraping process for the initial data."""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
# Removed unused import: from urllib.parse import quote_plus
import time # Keep time if used elsewhere, otherwise remove
import config

# --- Keep setup_driver ---
def setup_driver():
    """Initializes and returns a Selenium WebDriver instance."""
    print("Initializing Selenium WebDriver..."); options = webdriver.ChromeOptions()
    options.add_argument('--headless'); options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage'); options.add_argument('--log-level=3')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
    try:
        driver = webdriver.Chrome(options=options)
        print("WebDriver initialized.")
        return driver
    except Exception as e:
        print(f"Error initializing WebDriver: {e}")
        return None

def scrape_split_data(driver, url):
    """Navigates to the URL and scrapes the initial split data table."""
    if not driver:
        print("Error: WebDriver not initialized for initial scrape.")
        return [], [] # Return empty lists

    print(f"Navigating to {url} for initial split list...");
    table_element = None # Initialize table_element outside the try block

    # --- Try block for navigation and finding the main table ---
    try:
        driver.get(url)
        wait_time = config.SELENIUM_WAIT_TIME
        print(f"Waiting up to {wait_time}s for table...")
        # Adjust the ID if your table has a different ID
        table_element = WebDriverWait(driver, wait_time).until(
            EC.presence_of_element_located((By.ID, "latest_splits"))
        )
        WebDriverWait(table_element, wait_time).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "tbody tr"))
        )
        print("Initial table content detected.")

    # --- CORRECT INDENTATION: except blocks aligned with the try block above ---
    except TimeoutException:
        print(f"Error: Timed out waiting for initial table (ID: latest_splits) at {url}.")
        return [], [] # Return empty lists on timeout
    except Exception as nav_err:
        print(f"Error during navigation/wait for table: {nav_err}")
        return [], [] # Return empty lists on other navigation errors
    # --- End of except blocks ---

    # --- Header and Row extraction only proceed if the table was found ---
    if table_element is None:
        print("Error: table_element could not be found or assigned, cannot proceed with scraping.")
        return [], []

    headers = []
    try:
        thead = table_element.find_element(By.TAG_NAME, "thead")
        headers = [th.text.strip() for th in thead.find_elements(By.TAG_NAME, "th")]
        print(f"DEBUG: Headers: {headers}")
    except Exception as header_err:
        print(f"Warning: Could not parse initial table headers: {header_err}")

    all_row_data_values = []
    print("Extracting row data...")
    try:
        tbody = table_element.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")
        print(f"Found {len(rows)} rows.")
    except NoSuchElementException:
        print("Error: Could not find tbody.")
        # Return headers (if found) but empty data list
        return headers, []

    for i, row_element in enumerate(rows):
        try:
            cells = row_element.find_elements(By.TAG_NAME, "td")
            current_row_values = [(c.get_attribute('data-val') or c.text or '').strip() for c in cells]
            # Only append if row has any data to avoid empty lists
            if any(current_row_values):
                all_row_data_values.append(current_row_values)
        except StaleElementReferenceException:
            print(f"Warning: Row {i+1} became stale during processing. Skipping.")
            # Continue to the next row if one becomes stale
            continue
        except Exception as e:
            print(f"Warning: Error processing cells in row {i+1}: {e}. Skipping row.")
            # Continue to the next row if there's an error with cells
            continue

    print(f"Extracted data from {len(all_row_data_values)} non-empty rows from initial table.")
    return headers, all_row_data_values

# --- search_and_extract_google_text function is confirmed REMOVED ---