with open('app/job_agent.py', 'r') as f:
    text = f.read()

new_logic = """
            if not self.skills:
                job['match_score'] = 100
                filtered_jobs.append(job)
            elif job["match_score"] >= 70:
                filtered_jobs.append(job)
"""

text = text.replace('if job["match_score"] >= 70:\n                filtered_jobs.append(job)', new_logic.strip())

with open('app/job_agent.py', 'w') as f:
    f.write(text)
