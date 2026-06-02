# --- Imports ---
import requests
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import re
from typing import Optional, Tuple
from datetime import date, timedelta
from urllib.parse import quote_plus


def _normalize_skills(skills):
    return [skill.strip().lower() for skill in skills if skill and skill.strip()]


def _build_search_keyword(skills):
    normalized = _normalize_skills(skills)
    if not normalized:
        return ""
    # Each search call now only receives a 2-skill chunk, so use all of them.
    return " ".join(normalized)


def _extract_city(location: str) -> str:
    """
    Extract just the city name from a 'City, State' or 'City / City, State' label.
    Examples:
      'Bangalore / Bengaluru, Karnataka' → 'Bangalore'
      'Chennai, Tamil Nadu'              → 'Chennai'
      'Remote'                           → 'Remote'
    """
    loc = location.strip()
    # Strip state part (everything after last comma)
    if "," in loc:
        loc = loc.rsplit(",", 1)[0].strip()
    # For combined city labels like 'Bangalore / Bengaluru', use the first city
    if "/" in loc:
        loc = loc.split("/")[0].strip()
    return loc


def _build_naukri_url(designation, skills, location):
    """
    Build the best Naukri search URL.
    Strips state suffix and combined-city slashes so Naukri gets a clean city name.
    """
    loc = _extract_city(location)
    # Normalise Bangalore variants
    if loc.lower() in {"bengaluru", "bangalore/bengaluru", "bengaluru/bangalore"}:
        loc = "Bangalore"

    kw = designation.strip() if designation else ""
    if not kw and skills:
        kw = " ".join(skills[:2])
    k_param = quote_plus(kw) if kw else ""
    l_param = quote_plus(loc) if loc and loc.lower() not in {"remote", "hybrid", "pan india"} else ""
    if k_param and l_param:
        return f"https://www.naukri.com/jobs?k={k_param}&l={l_param}&sort=1"
    elif k_param:
        return f"https://www.naukri.com/jobs?k={k_param}&sort=1"
    else:
        return "https://www.naukri.com/jobs?sort=1"


def _matches_requested_skills(requested_skills, extracted_skills, text=""):
    requested = _normalize_skills(requested_skills)
    extracted = [skill.strip().lower() for skill in extracted_skills if skill]
    searchable_text = " ".join(extracted + [text.lower() if text else ""])

    if not requested:
        return True

    for skill in requested:
        if skill in searchable_text:
            return True
    return False


def _extract_experience_years(text: str) -> Optional[Tuple[int, int]]:
    """Extract an experience range (min_years, max_years) from text.

    Supports patterns like:
    - "2-5 Yrs", "2 - 5 years"
    - "3+ years"
    - "Minimum 4 years"
    - "5 years experience"
    """
    if not text:
        return None

    normalized = " ".join(text.split())

    range_match = re.search(
        r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:yrs?|years?)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if range_match:
        min_years = int(range_match.group(1))
        max_years = int(range_match.group(2))
        if min_years > max_years:
            min_years, max_years = max_years, min_years
        return (min_years, max_years)

    plus_match = re.search(
        r"\b(\d{1,2})\s*\+\s*(?:yrs?|years?)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if plus_match:
        min_years = int(plus_match.group(1))
        return (min_years, min_years)

    min_match = re.search(
        r"\b(?:min(?:imum)?\s*)?(\d{1,2})\s*(?:yrs?|years?)\s*(?:of\s*)?(?:exp(?:erience)?)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if min_match:
        years = int(min_match.group(1))
        return (years, years)

    return None


def _job_matches_experience(job: dict, required_years: int) -> bool:
    exp_min = job.get("experience_min")
    exp_max = job.get("experience_max")
    if exp_min is None and exp_max is None:
        return True # Soft filter: if we don't know the required experience, let it pass

    if exp_min is None:
        exp_min = exp_max
    if exp_max is None:
        exp_max = exp_min

    try:
        return int(exp_min) <= required_years <= int(exp_max)
    except Exception:
        return True # Let invalid strings pass


def _extract_posted_days_ago(text: str) -> Optional[int]:
    """Extract how many days ago a job was posted from a text blob.

    Supports patterns like:
    - "Posted 3 days ago", "3 days ago", "1 day ago"
    - "Just posted", "Today" -> 0
    - "Yesterday" -> 1
    - "30+ days ago" -> 30
    - "5 hours ago" -> 0
    """
    if not text:
        return None

    normalized = " ".join(text.split()).lower()

    if "just posted" in normalized or "today" in normalized:
        return 0
    if "yesterday" in normalized:
        return 1

    plus_days = re.search(r"\b(\d{1,3})\s*\+\s*days?\s*ago\b", normalized)
    if plus_days:
        return int(plus_days.group(1))

    days = re.search(r"\b(\d{1,3})\s*days?\s*ago\b", normalized)
    if days:
        return int(days.group(1))

    weeks = re.search(r"\b(\d{1,3})\s*weeks?\s*ago\b", normalized)
    if weeks:
        return int(weeks.group(1)) * 7

    months = re.search(r"\b(\d{1,3})\s*months?\s*ago\b", normalized)
    if months:
        return int(months.group(1)) * 30

    hours = re.search(r"\b(\d{1,3})\s*hours?\s*ago\b", normalized)
    if hours:
        return 0

    return None


def _job_matches_posted_within(job: dict, within_days: int) -> bool:
    days_ago = job.get("posted_days_ago")
    posted_date = job.get("posted_date")

    if days_ago is None and posted_date:
        try:
            d = date.fromisoformat(str(posted_date)[:10])
            days_ago = (date.today() - d).days
        except Exception:
            days_ago = None

    if days_ago is None:
        return True # Soft filter: if we don't know the post date, let it pass

    try:
        return int(days_ago) <= within_days
    except Exception:
        return True # Let invalid strings pass


# --- Naukri.com Fetcher ---
import time
import os

def fetch_naukri_jobs_playwright(skills, location="", designation="", email="", password=""):
    """
    Fetch jobs from Naukri.com using query-param URL format for maximum accuracy.
    Scrapes up to 3 pages (≈60 results). Auto-logins if credentials provided.
    """
    jobs = []
    naukri_url = _build_naukri_url(designation, skills, location)
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                headless=True,
                args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"]
            )
            try:
                context = browser.new_context(user_agent=user_agent)
                page = context.new_page()
                Stealth().apply_stealth_sync(page)

                # Auto-login to Naukri if credentials are provided
                if email and password:
                    try:
                        page.goto("https://www.naukri.com/nlogin/login", timeout=20000)
                        page.wait_for_selector("input#usernameField", timeout=8000)
                        page.fill("input#usernameField", email)
                        page.fill("input#passwordField", password)
                        page.click("button[type=submit]")
                        page.wait_for_timeout(2500)
                        print("[naukri] Logged in successfully.")
                    except Exception as login_err:
                        print(f"[naukri] Login skipped: {login_err}")

                seen_urls = set()
                # Scrape up to 3 pages (page param is &pageNo=N for query-param URLs)
                for page_num in range(1, 4):
                    paged_url = f"{naukri_url}&pageNo={page_num}" if page_num > 1 else naukri_url
                    try:
                        page.goto(paged_url, timeout=30000)
                    except Exception:
                        break

                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.8)

                    try:
                        page.wait_for_selector(
                            "div.srp-jobtuple-wrapper, article.jobTuple, div.cust-job-tuple",
                            timeout=10000
                        )
                    except Exception:
                        pass

                    soup = BeautifulSoup(page.content(), "html.parser")
                    job_cards = (
                        soup.find_all("div", class_="srp-jobtuple-wrapper") or
                        soup.find_all("article", class_="jobTuple") or
                        soup.find_all("div", class_="cust-job-tuple")
                    )

                    if not job_cards:
                        break  # No more results

                    for div in job_cards:
                        card_text = div.get_text(" ", strip=True)
                        exp_range = _extract_experience_years(card_text)
                        posted_days_ago = _extract_posted_days_ago(card_text)
                        posted_date = (
                            (date.today() - timedelta(days=posted_days_ago)).isoformat()
                            if posted_days_ago is not None else None
                        )

                        title_tag = div.find("a", class_="title")
                        comp_wrap = div.find("span", class_="comp-dtls-wrap") or div.find("div", class_="companyInfo")
                        company_tag = None
                        if comp_wrap:
                            company_tag = comp_wrap.find("a", class_="comp-name") or comp_wrap.find("a", class_="subTitle")

                        loc_tag = (
                            div.find("span", class_="locWdth") or
                            div.find("li", class_="location") or
                            div.find("span", class_="loc")
                        )
                        job_location = loc_tag.text.strip() if loc_tag else "N/A"

                        skills_ul = div.find("ul", class_="tags-gt") or div.find("ul", class_="has-description")
                        job_skills = [li.text.strip() for li in skills_ul.find_all("li")] if skills_ul else []

                        job_title = title_tag.text.strip() if title_tag else ""

                        job_url = None
                        if title_tag and title_tag.has_attr("href"):
                            job_url = title_tag["href"]
                            if job_url and not job_url.startswith("http"):
                                job_url = "https://www.naukri.com" + job_url
                        if not job_url:
                            for a_tag in div.find_all("a", href=True):
                                href = a_tag["href"]
                                if href and ("/job-listings-" in href or "naukri.com" in href):
                                    job_url = href if href.startswith("http") else "https://www.naukri.com" + href
                                    break

                        # Deduplicate within this fetch
                        url_key = (job_url or "").split("?")[0]
                        if url_key and url_key in seen_urls:
                            continue
                        if url_key:
                            seen_urls.add(url_key)

                        if not job_title:
                            continue

                        jobs.append({
                            "title": job_title,
                            "company": company_tag.text.strip() if company_tag else "N/A",
                            "location": job_location,
                            "skills": job_skills,
                            "url": job_url,
                            "source": "Naukri",
                            "experience_min": exp_range[0] if exp_range else None,
                            "experience_max": exp_range[1] if exp_range else None,
                            "posted_days_ago": posted_days_ago,
                            "posted_date": posted_date,
                        })

            finally:
                browser.close()

    except Exception as main_e:
        print(f"[Naukri Fetcher] Top-level error: {main_e}")

    return jobs


def _playwright_linkedin_fetch(jobs_list, base_url, email, password, seen_urns):
    """Login to LinkedIn via Playwright and scrape job cards."""
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = browser.new_context(user_agent=ua)
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            # Login
            page.goto("https://www.linkedin.com/login", timeout=20000)
            page.wait_for_selector("input#username", timeout=8000)
            page.fill("input#username", email)
            page.fill("input#password", password)
            page.click("button[type=submit]")
            page.wait_for_timeout(3000)
            print("[linkedin] Logged in.")
            # Fetch jobs page
            for start in [0, 25]:
                url = f"{base_url}&start={start}"
                page.goto(url, timeout=20000)
                page.wait_for_timeout(2000)
                soup = BeautifulSoup(page.content(), "html.parser")
                for card in soup.find_all("div", class_="base-card"):
                    urn = card.get("data-entity-urn", "")
                    if not urn or urn in seen_urns:
                        continue
                    seen_urns.add(urn)
                    info = card.find("div", class_="base-search-card__info")
                    if not info:
                        continue
                    title_el = info.find("h3")
                    company_el = info.find("h4")
                    loc_el = info.find("span", class_="job-search-card__location")
                    a_el = card.find("a", href=True)
                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    location_str = loc_el.get_text(strip=True) if loc_el else ""
                    job_url = a_el["href"] if a_el else ""
                    if title:
                        jobs_list.append({
                            "title": title, "company": company, "location": location_str,
                            "url": job_url, "skills": [], "source": "LinkedIn",
                            "apply_type": "LinkedIn Apply",
                        })
        finally:
            browser.close()


# --- LinkedIn Fetcher ---
def fetch_linkedin_jobs(skills, location="", designation="", email="", password=""):
    """
    Fetch jobs from LinkedIn.
    Strategy: designation is the primary search keyword (most accurate for title matching).
    Skills are used for post-fetch scoring only — NOT in the search query.
    Scrapes up to 10 pages (250 results) across Easy Apply + All Jobs.
    Falls back to skills-based search if designation-only returns nothing.
    """
    jobs = []
    seen_urns = set()

    # Build keyword: designation only first (most accurate), fall back to skills
    primary_kw = designation.strip() if designation else _build_search_keyword(skills)
    # Extract just the city name for LinkedIn search (strip ", State" suffix)
    loc_city = _extract_city(location) if location else ""
    loc_param = f"&location={quote_plus(loc_city)}" if loc_city and loc_city.lower() not in {"remote","hybrid","pan india"} else ""
    base_url = f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(primary_kw)}{loc_param}&sortBy=DD"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    # If credentials provided, try Playwright authenticated scrape first
    if email and password:
        try:
            _playwright_linkedin_fetch(jobs, base_url, email, password, seen_urns)
            if jobs:
                return jobs
        except Exception as e:
            print(f"[linkedin] Playwright login fetch failed, falling back to anonymous: {e}")

    def _scrape_pages(search_url, easy_apply=False):
        """Scrape up to 10 pages from a single search URL."""
        start_offset = 0
        pages_fetched = 0
        while pages_fetched < 10:
            url = f"{search_url}&start={start_offset}"
            if easy_apply:
                url += "&f_AL=true"

            try:
                resp = requests.get(url, headers=headers, timeout=15)
            except Exception:
                break
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = soup.find_all("div", class_="base-card")
            if not job_cards:
                break

            pages_fetched += 1
            start_offset += len(job_cards)

            for div in job_cards:
                urn = div.get("data-entity-urn", "")
                if not urn or urn in seen_urns:
                    continue
                seen_urns.add(urn)

                info = div.find("div", class_="base-search-card__info")
                if not info:
                    continue

                card_text = info.get_text(" ", strip=True)
                card_lower = card_text.lower()
                if any(sig in card_lower for sig in [
                    "no longer accepting applications",
                    "no longer available",
                    "position has been filled",
                    "has hired for this role",
                    "applications are closed",
                ]):
                    continue

                exp_range = _extract_experience_years(card_text)
                posted_days_ago = None
                posted_date = None
                time_tag = info.find("time")
                if time_tag is not None:
                    dt = time_tag.get("datetime")
                    if dt:
                        posted_date = dt.strip()
                    else:
                        posted_days_ago = _extract_posted_days_ago(time_tag.get_text(" ", strip=True))
                if posted_days_ago is None and posted_date is None:
                    posted_days_ago = _extract_posted_days_ago(card_text)
                if posted_date is None and posted_days_ago is not None:
                    posted_date = (date.today() - timedelta(days=posted_days_ago)).isoformat()
                if posted_days_ago is None and posted_date is not None:
                    try:
                        d = date.fromisoformat(str(posted_date)[:10])
                        posted_days_ago = (date.today() - d).days
                    except Exception:
                        posted_days_ago = None

                title_tag = info.find("h3", class_="base-search-card__title")
                company_tag = info.find("h4", class_="base-search-card__subtitle")
                location_tag = info.find("span", class_="job-search-card__location")
                job_title = title_tag.text.strip() if title_tag else ""

                job_url = None
                a_tag = div.find("a", href=True)
                if a_tag:
                    job_url = a_tag["href"]
                if not job_url:
                    for a in info.find_all("a", href=True):
                        if "linkedin.com/jobs/view" in a["href"] or a["href"].startswith("/jobs/view/"):
                            job_url = a["href"]
                            break
                if job_url and job_url.startswith("/"):
                    job_url = "https://www.linkedin.com" + job_url
                if job_url and "?" in job_url:
                    job_url = job_url.split("?")[0]

                # Approximate skill tags: check which user-skills appear in title/card
                extracted_skills = []
                search_text = (job_title + " " + card_text).lower()
                for s in skills:
                    if re.search(r'(?<![a-z0-9])' + re.escape(s.lower()) + r'(?![a-z0-9])', search_text):
                        extracted_skills.append(s)

                jobs.append({
                    "title": job_title or "N/A",
                    "company": company_tag.text.strip() if company_tag else "N/A",
                    "location": location_tag.text.strip() if location_tag else "N/A",
                    "skills": extracted_skills,
                    "snippet": card_text,
                    "description": "",
                    "url": job_url,
                    "source": "LinkedIn",
                    "apply_type": "Easy Apply" if easy_apply else "Apply on company site",
                    "experience_min": exp_range[0] if exp_range else None,
                    "experience_max": exp_range[1] if exp_range else None,
                    "posted_days_ago": posted_days_ago,
                    "posted_date": posted_date,
                })

    try:
        # Pass 1: Easy Apply only (highest apply-rate jobs)
        _scrape_pages(base_url, easy_apply=True)
        # Pass 2: All jobs (includes non-Easy-Apply)
        _scrape_pages(base_url, easy_apply=False)

        # Fallback: if designation-only returned no results, retry with top 2 skills added
        if not jobs and skills:
            fallback_kw = f"{primary_kw} {' '.join(skills[:2])}".strip()
            fallback_url = f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(fallback_kw)}{loc_param}&sortBy=DD"
            _scrape_pages(fallback_url, easy_apply=True)
            _scrape_pages(fallback_url, easy_apply=False)

    except Exception as e:
        jobs.append(
            {
                "title": "LinkedIn fetch error",
                "skills": [],
                "error": str(e),
                "source": "LinkedIn",
                "apply_type": "None",
            }
        )

    return jobs


def _skill_chunks(skills, max_chunks=2):
    """
    Split skills into at most `max_chunks` groups for multi-query searches.
    Each group contains a balanced portion of the skills list.
    Keeps Naukri/LinkedIn search calls low (Playwright is slow) while ensuring
    ALL skills drive at least one search query.
    """
    normalized = _normalize_skills(skills)
    if not normalized:
        return [""]
    if len(normalized) <= 3 or max_chunks == 1:
        return [" ".join(normalized[:4])]  # single query with top 4

    mid = len(normalized) // 2
    first_half = " ".join(normalized[:mid])
    second_half = " ".join(normalized[mid:mid + 4])  # cap second group at 4 more
    return [first_half, second_half]


def _dedupe_jobs(jobs):
    """Remove duplicate jobs by URL; fall back to title+company deduplication."""
    seen_urls = set()
    seen_tc = set()
    unique = []
    for job in jobs:
        url = (job.get("url") or "").strip().split("?")[0]
        tc = (str(job.get("title", "")).lower().strip(), str(job.get("company", "")).lower().strip())

        if url and url in seen_urls:
            continue
        if tc[0] and tc in seen_tc:
            continue

        if url:
            seen_urls.add(url)
        if tc[0]:
            seen_tc.add(tc)
        unique.append(job)
    return unique


# --- Aggregator ---
def fetch_jobs(
    skills,
    designation="",
    location="",
    experience_years: Optional[int] = None,
    posted_within_days: Optional[int] = None,
    credentials: dict = None,
):
    """
    Fetch jobs from both Naukri and LinkedIn.

    Strategy for 99%+ accuracy:
    - LinkedIn: designation-only keyword (title matching is most accurate); 
      fallback adds top 2 skills if no results.
    - Naukri: query-param URL (?k=designation&l=location) — far more reliable
      than the fragile slug format.
    - Both sources scrape significantly more pages (LinkedIn: 10 pages,
      Naukri: 3 pages) compared to the old approach.
    - Skills are used for post-fetch ATS scoring, not search query construction.
    - All results are deduplicated before filtering/sorting.
    """
    import threading
    jobs = []
    jobs_lock = threading.Lock()
    creds = credentials or {}
    li_email  = creds.get("linkedin_email", "")
    li_pass   = creds.get("linkedin_password", "")
    nk_email  = creds.get("naukri_email", "")
    nk_pass   = creds.get("naukri_password", "")

    # Location may use '||' separator (from chip input) or just be a single "City, State" value
    # Split only on '||' to keep "City, State" intact as a single location
    locations = [loc.strip() for loc in location.split("||") if loc.strip()]
    if not locations:
        locations = [""]

    def _run_linkedin(loc):
        try:
            results = fetch_linkedin_jobs(skills, loc, designation,
                                          email=li_email, password=li_pass)
            with jobs_lock:
                jobs.extend(results)
        except Exception as e:
            with jobs_lock:
                jobs.append({
                    "title": "LinkedIn fetch error", "company": "", "location": loc,
                    "skills": [], "url": "", "error": str(e), "source": "LinkedIn"
                })

    def _run_naukri(loc):
        try:
            results = fetch_naukri_jobs_playwright(skills, loc, designation,
                                                   email=nk_email, password=nk_pass)
            with jobs_lock:
                jobs.extend(results)
        except Exception as e:
            with jobs_lock:
                jobs.append({
                    "title": "Naukri fetch error", "company": "", "location": loc,
                    "skills": [], "url": "", "error": str(e), "source": "Naukri",
                })

    threads = []
    for loc in locations:
        t1 = threading.Thread(target=_run_linkedin, args=(loc,))
        t2 = threading.Thread(target=_run_naukri, args=(loc,))
        threads.extend([t1, t2])
        t1.start()
        t2.start()

    for t in threads:
        t.join(timeout=120)  # increased timeout for 10-page LinkedIn scrape

    # Deduplicate across all search calls
    jobs = _dedupe_jobs(jobs)

    if experience_years is not None:
        jobs = [job for job in jobs if _job_matches_experience(job, experience_years)]

    if posted_within_days is not None:
        jobs = [job for job in jobs if _job_matches_posted_within(job, posted_within_days)]

    # Sort latest-first
    jobs.sort(key=lambda j: j.get("posted_days_ago") if j.get("posted_days_ago") is not None else 9999)

    return jobs


# --- Helper: Find common jobs between sources ---
def find_common_jobs(jobs):
    """
    Find jobs that appear on both LinkedIn and Naukri by matching title and company (case-insensitive).
    Returns a list of common jobs (dicts with title, company, and sources).
    """
    seen = {}
    common = []
    for job in jobs:
        key = (job.get("title", "").strip().lower(), job.get("company", "").strip().lower())
        source = job.get("source", "")
        if key in seen and seen[key] != source:
            common.append(
                {
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "sources": sorted([seen[key], source]),
                }
            )
        else:
            seen[key] = source
    return common
