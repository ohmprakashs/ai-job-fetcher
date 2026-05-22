import os

with open("app/auto_apply_bot.py", "r") as f:
    content = f.read()

# Replace get_unapplied_jobs
new_get_unapplied = """def get_unapplied_jobs(platform='all', designation='', skills=None):
    if skills is None:
        skills = []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    query = "SELECT * FROM jobs WHERE is_applied = 0 AND url IS NOT NULL AND url != ''"
    if platform.lower() == 'naukri':
        query += " AND source='Naukri'"
    elif platform.lower() == 'linkedin':
        query += " AND source='LinkedIn'"
        
    c.execute(query)
    all_jobs = [dict(r) for r in c.fetchall()]
    conn.close()
    
    # Filter by > 70% match score if skills are provided
    filtered_jobs = []
    lower_skills = [s.lower() for s in skills]
    designation_lower = designation.lower()
    
    for job in all_jobs:
        score = 0
        job_title_lower = str(job.get("title", "")).lower()
        
        # Parse skills column
        import ast
        job_skills_lower = []
        try:
            val = job.get("skills", "[]")
            if val.startswith('['):
                parsed = ast.literal_eval(val)
                job_skills_lower = [str(x).lower() for x in parsed]
            else:
                job_skills_lower = [val.lower()]
        except:
            pass
            
        if lower_skills:
            matches = 0
            for skill in lower_skills:
                if skill in job_skills_lower or skill in job_title_lower:
                    matches += 1
            score = int((matches / len(lower_skills)) * 100)
            
        if designation_lower and designation_lower in job_title_lower:
            score += min(100 - score, 20)
            
        # Only apply if match score is > 70%
        if score > 70:
            job['match_score'] = score
            filtered_jobs.append(job)
            
    filtered_jobs.sort(key=lambda x: x['match_score'], reverse=True)
    return filtered_jobs[:5] # Limit to top 5 to avoid long blockages
"""

content = content.replace("def get_unapplied_jobs():\n    conn = sqlite3.connect(DB_PATH)\n    conn.row_factory = sqlite3.Row\n    c = conn.cursor()\n    # ONLY pull Naukri positions for the LLM! LinkedIn has heavy anti-bot blocking\n    c.execute(\"SELECT * FROM jobs WHERE is_applied = 0 AND source='Naukri' AND url IS NOT NULL AND url != '' LIMIT 3\")\n    jobs = [dict(r) for r in c.fetchall()]\n    conn.close()\n    return jobs", new_get_unapplied)

content = content.replace("async def async_run_auto_apply():\n    jobs = get_unapplied_jobs()", "async def async_run_auto_apply(platform='all', designation='', skills=None):\n    jobs = get_unapplied_jobs(platform, designation, skills)")

content = content.replace("def run_auto_apply():\n    # Flask triggers this in a background thread\n    # We must use asyncio.run to kickstart the async LLM agent loop\n    asyncio.run(async_run_auto_apply())", "def run_auto_apply(platform='all', designation='', skills=None):\n    # Flask triggers this in a background thread\n    # We must use asyncio.run to kickstart the async LLM agent loop\n    asyncio.run(async_run_auto_apply(platform, designation, skills))")

with open("app/auto_apply_bot.py", "w") as f:
    f.write(content)
