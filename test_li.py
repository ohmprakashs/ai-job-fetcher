import sys
import os
from playwright.sync_api import sync_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(__file__), "playwright_profile")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=True,
        args=[
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1920,1080"
        ]
    )
    page = browser.new_page()
    page.goto("https://www.linkedin.com/jobs/search/?keywords=python&location=India&sortBy=DD")
    page.wait_for_timeout(3000)
    html = page.content()
    with open("li_test.html", "w") as f:
        f.write(html)
    browser.close()
