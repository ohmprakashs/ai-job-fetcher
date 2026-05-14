# --- Imports ---
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import re
from typing import Optional, Tuple
from datetime import date, timedelta


def _normalize_skills(skills):
    return [skill.strip().lower() for skill in skills if skill and skill.strip()]


def _build_search_keyword(skills):
    normalized = _normalize_skills(skills)
    if not normalized:
        return "python"
    return " ".join(normalized)


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
        return False

    if exp_min is None:
        exp_min = exp_max
    if exp_max is None:
        exp_max = exp_min

    try:
        return int(exp_min) <= required_years <= int(exp_max)
    except Exception:
        return False


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
        return False

    try:
        return int(days_ago) <= within_days
    except Exception:
        return False
    if exp_min is None:
        exp_min = exp_max
    if exp_max is None:
        exp_max = exp_min
    try:
        return int(exp_min) <= required_years <= int(exp_max)
    except Exception:
        return False


# --- Naukri.com Fetcher ---
import time
import os

def fetch_naukri_jobs_playwright(skills, location="", designation=""):
    """
    Fetch jobs from Naukri.com matching the given skills using Playwright + stealth.
    """
    jobs = []
    keyword = designation if designation else _build_search_keyword(skills)
    loc_path = f"-in-{location.strip().replace(' ', '-').lower()}" if location else ""
    naukri_url = f"https://www.naukri.com/{keyword.replace(' ', '-')}-jobs{loc_path}"

    # Using a modern User-Agent helps avoid blocks
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    try:
        with sync_playwright() as p:
            # We use local Chrome to avoid downloading blocked Chromium binaries from googleapis
            browser = p.chromium.launch(
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                headless=True,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1920,1080"
                ]
            )
            try:
                context = browser.new_context(user_agent=user_agent)
                page = context.new_page()
                Stealth().apply_stealth_sync(page)

                for page_num in range(1, 4):  # Loop up to 3 pages to avoid Flask timeouts
                    current_url = naukri_url if page_num == 1 else f"{naukri_url}-{page_num}"
                    try:
                        page.goto(current_url, timeout=60000)
                    except:
                        break
                    
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    import time
                    time.sleep(2)
                    
                    try:
                        page.wait_for_selector("div.srp-jobtuple-wrapper, article.jobTuple, div.cust-job-tuple", timeout=10000)
                    except:
                        pass
                        
                    soup = BeautifulSoup(page.content(), "html.parser")
                    job_cards = soup.find_all("div", class_="srp-jobtuple-wrapper")
                    if not job_cards:
                        job_cards = soup.find_all("article", class_="jobTuple")
                    if not job_cards:
                        job_cards = soup.find_all("div", class_="cust-job-tuple")
                    
                    if not job_cards:
                        break  # Stop if no jobs found on this page
                    
                for div in job_cards:
                    card_text = div.get_text(" ", strip=True)
                    exp_range = _extract_experience_years(card_text)
                    posted_days_ago = _extract_posted_days_ago(card_text)
                    posted_date = (
                        (date.today() - timedelta(days=posted_days_ago)).isoformat()
                        if posted_days_ago is not None
                        else None
                    )
                    title_tag = div.find("a", class_="title")
                    comp_wrap = div.find("span", class_="comp-dtls-wrap") or div.find("div", class_="companyInfo")
                    company_tag = None
                    if comp_wrap:
                        company_tag = comp_wrap.find("a", class_="comp-name") or comp_wrap.find("a", class_="subTitle")

                    loc_tag = div.find("span", class_="locWdth") or div.find("li", class_="location") or div.find("span", class_="loc")
                    job_location = loc_tag.text.strip() if loc_tag else "N/A"

                    skills_ul = div.find("ul", class_="tags-gt") or div.find("ul", class_="has-description")
                    job_skills = [li.text.strip().lower() for li in skills_ul.find_all("li")] if skills_ul else []

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

                    jobs.append(
                        {
                            "title": title_tag.text.strip() if title_tag else "N/A",
                            "company": company_tag.text.strip() if company_tag else "N/A",
                            "location": job_location,
                            "skills": job_skills,
                            "url": job_url,
                            "source": "Naukri",
                            "experience_min": exp_range[0] if exp_range else None,
                            "experience_max": exp_range[1] if exp_range else None,
                            "posted_days_ago": posted_days_ago,
                            "posted_date": posted_date,
                        }
                    )
            finally:
                browser.close()

    except Exception as main_e:
        print(f"[Naukri Fetcher] Top-level error: {main_e}")
            
    return jobs


# --- LinkedIn Fetcher ---
def fetch_linkedin_jobs(skills, location="", designation=""):
    """
    Fetch jobs from LinkedIn matching the given skills using requests and BeautifulSoup.
    Checks Easy Apply and Apply on company site using f_AL parameter.
    """
    jobs = []
    keyword = designation if designation else _build_search_keyword(skills)
    loc_param = f"&location={location.strip().replace(' ', '%20')}" if location else ""
    base_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}{loc_param}&sortBy=DD"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    seen_urns = set()

    try:
        for is_easy_apply in [True, False]:
            start_offset = 0
            while start_offset < 100:  # Fetch up to 4 pages each
                url = f"{base_url}&start={start_offset}"
                if is_easy_apply:
                    url += "&f_AL=true"
                
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    break
                    
                soup = BeautifulSoup(resp.text, "html.parser")
                job_cards = soup.find_all("div", class_="base-card")
                if not job_cards:
                     break
                
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

                    apply_type = "Easy Apply" if is_easy_apply else "Apply on company site"

                    jobs.append(
                        {
                            "title": job_title or "N/A",
                            "company": company_tag.text.strip() if company_tag else "N/A",
                            "location": location_tag.text.strip() if location_tag else "N/A",
                            "skills": [],
                            "url": job_url,
                            "source": "LinkedIn",
                            "apply_type": apply_type,
                            "experience_min": exp_range[0] if exp_range else None,
                            "experience_max": exp_range[1] if exp_range else None,
                            "posted_days_ago": posted_days_ago,
                            "posted_date": posted_date,
                        }
                    )
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


# --- Aggregator ---
def fetch_jobs(
    skills,
    designation="",
    location="",
    experience_years: Optional[int] = None,
    posted_within_days: Optional[int] = None,
):
    """
    Fetch jobs from both Naukri and LinkedIn, combining results.
    Handles multiple comma-separated locations.
    """
    jobs = []
    
    locations = [loc.strip() for loc in location.split(",") if loc.strip()]
    if not locations:
        locations = [""]
        
    for loc in locations:
        try:
            jobs.extend(fetch_linkedin_jobs(skills, loc, designation))
        except Exception as e:
            jobs.append({
                "title": "LinkedIn fetch error", "company": "", "location": loc,
                "skills": [], "url": "", "error": str(e), "source": "LinkedIn"
            })
            
        try:
            jobs.extend(fetch_naukri_jobs_playwright(skills, loc, designation))
        except Exception as e:
            jobs.append({
                "title": "Naukri fetch error", "company": "", "location": loc,
                "skills": [], "url": "", "error": str(e), "source": "Naukri",
            })

    if experience_years is not None:
        jobs = [job for job in jobs if _job_matches_experience(job, experience_years)]

    if posted_within_days is not None:
        jobs = [job for job in jobs if _job_matches_posted_within(job, posted_within_days)]

    # Softly sort all jobs across platforms to ensure the latest ones are at the top
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
