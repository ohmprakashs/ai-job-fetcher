with open("app/job_db.py", "r") as f:
    text = f.read()

text = text.replace('("posted_days_ago", "INTEGER"), ("posted_date", "TEXT")]', '("posted_days_ago", "INTEGER"), ("posted_date", "TEXT"), ("apply_type", "TEXT")]')

old_insert = '''        c.execute("""
            INSERT INTO jobs (title, company, location, skills, url, source, experience_min, experience_max, posted_days_ago, posted_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(title, company, location, source) DO UPDATE SET
            skills=excluded.skills,
            url=excluded.url,
            experience_min=excluded.experience_min,
            experience_max=excluded.experience_max,
            posted_days_ago=excluded.posted_days_ago,
            posted_date=excluded.posted_date
        """, (
            job.get("title", ""), job.get("company", ""), job.get("location", ""),
            skills_str, job.get("url", ""), job.get("source", ""),
            job.get("experience_min"), job.get("experience_max"),
            job.get("posted_days_ago"), job.get("posted_date")
        ))'''

new_insert = '''        c.execute("""
            INSERT INTO jobs (title, company, location, skills, url, source, experience_min, experience_max, posted_days_ago, posted_date, apply_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(title, company, location, source) DO UPDATE SET
            skills=excluded.skills,
            url=excluded.url,
            experience_min=excluded.experience_min,
            experience_max=excluded.experience_max,
            posted_days_ago=excluded.posted_days_ago,
            posted_date=excluded.posted_date,
            apply_type=excluded.apply_type
        """, (
            job.get("title", ""), job.get("company", ""), job.get("location", ""),
            skills_str, job.get("url", ""), job.get("source", ""),
            job.get("experience_min"), job.get("experience_max"),
            job.get("posted_days_ago"), job.get("posted_date"), job.get("apply_type", "")
        ))'''
text = text.replace(old_insert, new_insert)

with open("app/job_db.py", "w") as f:
    f.write(text)
print("Updated job_db.py")
