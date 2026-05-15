from app.job_fetcher import fetch_linkedin_jobs
jobs = fetch_linkedin_jobs(skills=["python"])
print(f"Total LinkedIn jobs fetched: {len(jobs)}")
import collections
counts = collections.Counter(j.get("apply_type") for j in jobs)
print(counts)
