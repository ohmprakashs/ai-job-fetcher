import re

with open('app/job_agent.py', 'r') as f:
    text = f.read()

text = text.replace('job_skills_lower = [str(s).lower() for s in job.get("skills", [])]', 'job_skills_lower = [str(s).lower().strip() for s in job.get("skills", [])]')
text = text.replace('job_skills_lower = [s.lower() for s in job.get("skills", [])]', 'job_skills_lower = [s.lower().strip() for s in job.get("skills", [])]')

with open('app/job_agent.py', 'w') as f:
    f.write(text)
