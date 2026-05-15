import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def scrape_jd_text(url, source):
    if not url: return ""
    text = ""
    source = source.lower()
    try:
        if 'linkedin' in source:
            # Guest URL works with simple requests
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            desc = soup.find("div", class_="description__text") or soup.find("div", class_="show-more-less-html__markup")
            if desc:
                text = desc.get_text(" ", strip=True)
                
        elif 'naukri' in source:
            # Needs playwright because of React/SPA
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    headless=True
                )
                page = browser.new_page(user_agent="Mozilla/5.0")
                page.goto(url, timeout=30000)
                # Various Naukri description classes
                selectors = [".job-desc", ".styles_JDC__...", ".styles_job-desc-container__..."]
                try:
                    page.wait_for_selector(".job-desc", timeout=5000)
                    text = page.locator(".job-desc").inner_text()
                except:
                    # fallback get body
                    text = page.locator("body").inner_text()
                browser.close()
    except Exception as e:
        print(f"Failed to scrape JD from {url}: {e}")
        pass
    return text
