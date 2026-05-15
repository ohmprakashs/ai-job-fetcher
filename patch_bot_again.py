with open('app/auto_apply_bot.py', 'r') as f:
    text = f.read()

import re

old_logic = r"""                for req_skill in job_required_skills:
                    has_it = False
                    for user_skill in lower_skills:
                        if user_skill in req_skill or req_skill in user_skill:
                            has_it = True
                            break
                    if has_it:
                        matches \+= 1
                score = int\(\(matches / max\(1, len\(job_required_skills\)\)\) \* 100\)"""

new_logic = """                for user_skill in lower_skills:
                    has_it = False
                    for req_skill in job_required_skills:
                        if user_skill in req_skill or req_skill in user_skill:
                            has_it = True
                            break
                    if not has_it and user_skill in job_title_lower:
                        has_it = True
                    if has_it:
                        matches += 1
                score = int((matches / max(1, len(lower_skills))) * 100)"""

text = re.sub(old_logic, new_logic, text, count=1)

with open('app/auto_apply_bot.py', 'w') as f:
    f.write(text)
