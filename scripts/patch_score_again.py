with open('app/job_agent.py', 'r') as f:
    text = f.read()

import re
old_logic = r"""                    for req_skill in job_required_skills:
                        # Does the user have this required skill\?
                        # Or does the user skill somewhat align\?
                        # Actually self\.skills = what user searched\.
                        # Wait, what if user search IS what user HAS\?
                        has_it = False
                        for user_skill in self\.skills:
                            if user_skill in req_skill or req_skill in user_skill:
                                has_it = True
                                break
                        if has_it:
                            matches \+= 1
                    
                    score = int\(\(matches / len\(job_required_skills\)\) \* 100\)"""

new_logic = """                    # Does the job have the user's skill?
                    for user_skill in self.skills:
                        has_it = False
                        for req_skill in job_required_skills:
                            if user_skill in req_skill or req_skill in user_skill:
                                has_it = True
                                break
                        if not has_it and user_skill in job_title_lower:
                            has_it = True
                        if has_it:
                            matches += 1
                    
                    score = int((matches / len(self.skills)) * 100)"""

text = re.sub(old_logic, new_logic, text, count=1)

with open('app/job_agent.py', 'w') as f:
    f.write(text)
