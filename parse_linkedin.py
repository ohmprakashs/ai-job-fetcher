import requests
from bs4 import BeautifulSoup

def test_fetch(keyword):
    url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}&location=Bangalore&sortBy=DD"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")
    job_cards = soup.find_all("div", class_="base-card")
    print(f"Found {len(job_cards)} jobs for {keyword}")
    
    if job_cards:
        info = job_cards[0].find("div", class_="base-search-card__info")
        print("\nRAW INFO TEXT:")
        print(info.get_text(" ", strip=True))

test_fetch("python")
