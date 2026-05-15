import requests
from bs4 import BeautifulSoup

def fetch_jd(url):
    print("Fetching", url)
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")
    # For LinkedIn:
    desc = soup.find("div", class_="description__text") or soup.find("div", class_="show-more-less-html__markup")
    if desc: return desc.get_text(" ", strip=True)
    # For Naukri:
    desc = soup.find("div", class_="job-desc") or soup.find("section", class_="job-desc")
    if desc: return desc.get_text(" ", strip=True)
    return "Could not parse JD"
    
print(fetch_jd("https://www.linkedin.com/jobs/view/4402184359"))
print(fetch_jd("https://www.naukri.com/job-listings-cloud-data-engineer-luxoft-india-llp-bengaluru-4-to-9-years-300426937370"))
