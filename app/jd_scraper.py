import re as _re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

_LI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_linkedin_job_id(url: str) -> str:
    """Extract the numeric job ID from any LinkedIn job URL.
    
    Handles both:
    - /jobs/view/4409787311/
    - /jobs/view/site-reliability-engineer-at-company-4409787311/
    """
    # The job ID is a long numeric sequence (7+ digits) at the end of the URL path
    m = _re.search(r'[-/](\d{7,})(?:[/?]|$)', url or "")
    return m.group(1) if m else ""


def scrape_jd_text(url, source):
    if not url: return ""
    text = ""
    source = source.lower()
    try:
        if 'linkedin' in source:
            # 1) Try the unauthenticated guest API — returns full JD HTML without login
            job_id = _extract_linkedin_job_id(url)
            if job_id:
                guest_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
                try:
                    resp = requests.get(guest_url, headers=_LI_HEADERS, timeout=10)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        desc = (
                            soup.find("div", class_="show-more-less-html__markup")
                            or soup.find("section", class_="description")
                            or soup.find("div", {"class": _re.compile(r"description", _re.I)})
                        )
                        if desc:
                            text = desc.get_text(" ", strip=True)
                except Exception:
                    pass

            # 2) Fallback: direct job page (sometimes works for public/cached pages)
            if not text:
                try:
                    resp = requests.get(url, headers=_LI_HEADERS, timeout=10)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        desc = (
                            soup.find("div", class_="show-more-less-html__markup")
                            or soup.find("div", class_="description__text")
                            or soup.find("section", class_="description")
                        )
                        if desc:
                            text = desc.get_text(" ", strip=True)
                except Exception:
                    pass
                
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
