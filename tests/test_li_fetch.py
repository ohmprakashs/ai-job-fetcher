import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

def test_li():
    keyword = "python"
    loc_param = "&location=India"
    base_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}{loc_param}&sortBy=DD"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    jobs = []
    seen_urns = set()
    
    # 1. Fetch Easy Apply
    for is_easy_apply in [True, False]:
        start_offset = 0
        while start_offset < 50:
            url = f"{base_url}&start={start_offset}"
            if is_easy_apply:
                url += "&f_AL=true"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200: break
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="base-card")
            if not cards: break
            start_offset += len(cards)
            for div in cards:
                urn = div.get("data-entity-urn", "")
                if not urn or urn in seen_urns: continue
                seen_urns.add(urn)
                
                info = div.find("div", class_="base-search-card__info")
                if not info: continue
                title_tag = info.find("h3", class_="base-search-card__title")
                title = title_tag.text.strip() if title_tag else "Unknown"
                
                apply_type = "Easy Apply" if is_easy_apply else "Apply on company site"
                jobs.append({
                    "title": title,
                    "apply_type": apply_type,
                    "urn": urn
                })

    print(f"Total jobs: {len(jobs)}")
    for j in jobs[:5]: print(j)
    
test_li()
