with open("app/job_fetcher.py", "r") as f:
    text = f.read()

old_str = """        try:
            jobs.extend(fetch_naukri_jobs_playwright(skills, loc, designation))
        except Exception as e:
            jobs.append({
                "title": "Naukri fetch error", "company": "", "location": loc,
                "skills": [], "url": "", "error": str(e), "source": "Naukri",
            })"""

new_str = """        try:
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
            })"""

text = text.replace(old_str, new_str)

with open("app/job_fetcher.py", "w") as f:
    f.write(text)
print("Updated fetch_jobs in job_fetcher.py")
