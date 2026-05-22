import os
from playwright.sync_api import sync_playwright

def get_nauk_jd(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True
        )
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_selector(".job-description", timeout=15000)
        desc = page.locator(".job-description").inner_text()
        browser.close()
        return desc

print(get_nauk_jd("https://www.naukri.com/job-listings-cloud-data-engineer-luxoft-india-llp-bengaluru-4-to-9-years-300426937370"))
