import re
with open("app/job_fetcher.py", "r") as f:
    text = f.read()

new_linkedin_fetcher = '''def fetch_linkedin_jobs(skills, location="", designation=""):
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

    return jobs'''

# find the start and end of fetch_linkedin_jobs
start_idx = text.find("def fetch_linkedin_jobs(")
end_idx = text.find("# --- Aggregator ---", start_idx)

if start_idx != -1 and end_idx != -1:
    new_text = text[:start_idx] + new_linkedin_fetcher + "\n\n\n" + text[end_idx:]
    with open("app/job_fetcher.py", "w") as f:
        f.write(new_text)
    print("Replaced fetch_linkedin_jobs successfully!")
else:
    print("Could not find start or end index.")
