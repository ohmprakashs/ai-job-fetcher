with open('app/auto_apply_bot.py', 'r') as f:
    text = f.read()

new_logic = """
        if lower_skills:
            matches = 0
            # Clean spaces from job tags
            job_required_skills = [s.strip() for s in job_skills_lower if len(s.strip()) > 1]
            
            if not job_required_skills:
                # Fallback to title matching
                for skill in lower_skills:
                    if skill in job_title_lower:
                        matches += 1
                score = min(100, int((matches / max(1, len(lower_skills))) * 100) + 50) if matches > 0 else 0
            else:
                for req_skill in job_required_skills:
                    has_it = False
                    for user_skill in lower_skills:
                        if user_skill in req_skill or req_skill in user_skill:
                            has_it = True
                            break
                    if has_it:
                        matches += 1
                score = int((matches / max(1, len(job_required_skills))) * 100)
"""

import re
# Regex to match the old block
text = re.sub(
    r'\s+if lower_skills:\n\s+matches = 0\n\s+for skill in lower_skills:\n\s+if skill in job_skills_lower or skill in job_title_lower:\n\s+matches \+= 1\n\s+score = int\(\(matches / len\(lower_skills\)\) \* 100\)',
    new_logic,
    text,
    count=1
)

with open('app/auto_apply_bot.py', 'w') as f:
    f.write(text)
