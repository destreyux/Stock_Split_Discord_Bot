# scraper.py
"""Handles the Selenium web scraping process."""

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
# from selenium.webdriver.chrome.service import Service as ChromeService # Optional
# from webdriver_manager.chrome import ChromeDriverManager # Optional
import config # Import constants

def setup_driver():
    """Initializes and returns a Selenium WebDriver instance."""
    print("Initializing Selenium WebDriver...")
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--log-level=3')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
    # --- Initialize Driver (ensure chromedriver is accessible) ---
    try:
        # Example: assumes chromedriver is in PATH
        driver = webdriver.Chrome(options=options)
        # If using Service object:
        # service = ChromeService(executable_path=ChromeDriverManager().install())
        # driver = webdriver.Chrome(service=service, options=options)
        print("WebDriver initialized.")
        return driver
    except Exception as e:
        print(f"Error initializing WebDriver: {e}")
        print("Ensure chromedriver is installed and accessible in your PATH or provide explicit path.")
        return None

def scrape_split_data(driver, url):
    """Navigates to the URL and scrapes the split data table."""
    if not driver:
        print("Error: WebDriver not initialized.")
        return [], [] # Return empty lists

    print(f"Navigating to {url}...")
    try:
        driver.get(url)
        wait_time = config.SELENIUM_WAIT_TIME
        print(f"Waiting up to {wait_time} seconds for table content...")
        table_element = WebDriverWait(driver, wait_time).until(
            EC.presence_of_element_located((By.ID, "latest_splits")) # Adjust ID if needed
        )
        WebDriverWait(table_element, wait_time).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "tbody tr"))
        )
        print("Table content detected.")
    except TimeoutException:
        print(f"Error: Timed out waiting for table content at {url}.")
        # driver.save_screenshot('timeout_error_scrape.png') # Optional
        return [], [] # Return empty lists on timeout
    except Exception as nav_err:
        print(f"Error during navigation or initial wait: {nav_err}")
        return [], []

    # --- Extract Headers ---
    headers = []
    try:
        thead = table_element.find_element(By.TAG_NAME, "thead")
        headers = [th.text.strip() for th in thead.find_elements(By.TAG_NAME, "th")]
        print(f"DEBUG: Extracted headers: {headers}")
    except Exception as header_err:
        print(f"Warning: Could not parse table headers: {header_err}")

    # --- Extract Row Data ---
    all_row_data_values = []
    print("Extracting data-val attributes from table rows...")
    try:
        tbody = table_element.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")
        print(f"Found {len(rows)} <tr> elements.")
    except NoSuchElementException:
        print("Error: Could not find <tbody> element within the table.")
        return headers, [] # Return headers but empty data

    for i, row_element in enumerate(rows):
        try:
            cells = row_element.find_elements(By.TAG_NAME, "td")
            current_row_values = [(c.get_attribute('data-val') or c.text or '').strip() for c in cells]
            if any(current_row_values):
                all_row_data_values.append(current_row_values)
        except StaleElementReferenceException:
            print(f"Warning: Row {i+1} stale. Skipping.")
        except Exception as e:
            print(f"Warning: Error extracting cells row {i+1}: {e}. Skipping.")

    print(f"Extracted data from {len(all_row_data_values)} non-empty rows.")
    return headers, all_row_data_values