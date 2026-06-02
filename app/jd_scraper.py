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

# Phrases LinkedIn shows when a job is closed
_EXPIRED_SIGNALS = [
    "no longer accepting applications",
    "has hired for this role",          # LinkedIn "position filled" signal
    "see who was hired",
    "position has been filled",
    "no longer available",
    "this job is no longer",
    "job has expired",
    "applications are closed",
    "not accepting applications",
    "this listing has been removed",
]

def _is_expired_text(text: str) -> bool:
    t = text.lower()
    return any(sig in t for sig in _EXPIRED_SIGNALS)


def _has_apply_button(soup) -> bool:
    """
    Returns True if the page contains an Apply / Easy Apply / Apply on Company Site button.
    This is the most reliable signal that a job is still accepting applications.
    """
    # Check for button with 'apply' in class name (LinkedIn guest API)
    apply_btn = soup.find(
        ["button", "a"],
        class_=lambda c: c and any("apply" in cls.lower() for cls in (c if isinstance(c, list) else [c]))
    )
    if apply_btn:
        return True
    # Check text-based apply signals
    page_lower = soup.get_text(" ", strip=True).lower()
    return any(sig in page_lower for sig in [
        "easy apply", "apply now", "apply on company site", "apply on companysitebutton",
        "sign in to apply", "continue to apply"
    ])


def _extract_linkedin_job_id(url: str) -> str:
    """Extract the numeric job ID from any LinkedIn job URL."""

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
    """
    Scrape the JD text for a job URL.
    Returns (text, is_expired) tuple.
    - text: the JD body text (empty string if unavailable)
    - is_expired: True if the job has no apply button OR shows closed signals
    """
    if not url:
        return "", False
    text = ""
    is_expired = False
    source = source.lower()
    try:
        if 'linkedin' in source:
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

                        # PRIMARY CHECK: does an Apply/Easy Apply button exist?
                        if not _has_apply_button(soup):
                            return "", True  # no apply button = not accepting applications

                        # SECONDARY CHECK: explicit expired text
                        if _is_expired_text(soup.get_text(" ", strip=True)):
                            return "", True

                        desc = (
                            soup.find("div", class_="show-more-less-html__markup")
                            or soup.find("section", class_="description")
                            or soup.find("div", {"class": _re.compile(r"description", _re.I)})
                        )
                        if desc:
                            text = desc.get_text(" ", strip=True)
                    elif resp.status_code == 404:
                        return "", True  # job removed
                except Exception:
                    pass

            # Fallback: direct job page
                except Exception:
                    pass

            # 2) Fallback: direct job page (sometimes works for public/cached pages)
            if not text:
                try:
                    resp = requests.get(url, headers=_LI_HEADERS, timeout=10)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        if not _has_apply_button(soup) or _is_expired_text(soup.get_text(" ", strip=True)):
                            return "", True
                        desc = (
                            soup.find("div", class_="show-more-less-html__markup")
                            or soup.find("div", class_="description__text")
                            or soup.find("section", class_="description")
                        )
                        if desc:
                            text = desc.get_text(" ", strip=True)
                    elif resp.status_code == 404:
                        return "", True
                except Exception:
                    pass

        elif 'naukri' in source:
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
                try:
                    page.wait_for_selector(".job-desc", timeout=5000)
                    text = page.locator(".job-desc").inner_text()
                except Exception:
                    text = page.locator("body").inner_text()
                if _is_expired_text(text):
                    is_expired = True
                    text = ""
                browser.close()
    except Exception as e:
        print(f"Failed to scrape JD from {url}: {e}")
    return text, is_expired

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
