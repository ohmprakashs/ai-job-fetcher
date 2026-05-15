import sqlite3
import ast
conn = sqlite3.connect('jobs.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT skills, title FROM jobs LIMIT 1")
job = dict(c.fetchone())

print("DB Skills:", repr(job.get('skills')))

skills = ["python", "docker", "kubernetes", "prometheus", "grafana"]
self_skills = [s.lower() for s in skills if s.strip()]

score = 0
job_title_lower = str(job.get("title", "")).lower()

raw_skills = job.get("skills", [])
print("Raw skills type:", type(raw_skills))

# In old code: job_skills_lower = [str(s).lower() for s in job.get("skills", [])]
if isinstance(raw_skills, str):
    # Try ast.literal_eval if it's a string representation of a list, e.g. "['Python', 'Docker']"
    if raw_skills.startswith('['):
        try:
             parsed = ast.literal_eval(raw_skills)
             job_skills_lower = [str(s).lower().strip() for s in parsed]
        except:
             job_skills_lower = [s.strip().lower() for s in raw_skills.split(',')]
    else:
         job_skills_lower = [s.strip().lower() for s in raw_skills.split(',')]
else:
    job_skills_lower = [str(s).lower() for s in raw_skills]

print("job_skills_lower:", job_skills_lower)

if self_skills:
    matches = 0
    for skill in self_skills:
        if skill in job_skills_lower or skill in job_title_lower:
            matches += 1
    score = int((matches / len(self_skills)) * 100)

print("Score:", score)
