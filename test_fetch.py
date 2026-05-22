import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
from ai_matcher import fetch_job_description
print("Fetching...")
print(fetch_job_description("https://www.linkedin.com/jobs/view/123456"))
