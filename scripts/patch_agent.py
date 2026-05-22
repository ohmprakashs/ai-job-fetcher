with open("app/job_agent.py", "r") as f:
    text = f.read()

old_str = "filtered_jobs.sort(key=lambda j: j.get('match_score', 0), reverse=True)"
new_str = "filtered_jobs.sort(key=lambda j: (j.get('posted_days_ago') if j.get('posted_days_ago') is not None else 9999, -j.get('match_score', 0)))"

if old_str in text:
    text = text.replace(old_str, new_str)
    with open("app/job_agent.py", "w") as f:
        f.write(text)
    print("Updated job_agent.py sorting")
else:
    print("Could not find sorting line in job_agent.py")
