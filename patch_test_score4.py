import sys
sys.path.insert(0, './app')
from job_agent import JobAIAgent
from job_fetcher import fetch_jobs

# Test what fetch_jobs returns for Python/Django
raw_jobs = fetch_jobs(["python", "django", "aws", "docker"], designation="Backend")
print(f"Fetch Jobs returned {len(raw_jobs)} jobs.")
for job in raw_jobs[:3]:
    print(job['title'], job['skills'])

