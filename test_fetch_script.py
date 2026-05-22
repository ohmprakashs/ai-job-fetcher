with open("app/job_fetcher.py", "r") as f:
    for i, line in enumerate(f):
        if "skill" in line.lower():
            print(f"{i+1}: {line.strip()}")
