with open('app/job_agent.py', 'r') as f:
    text = f.read()

new_logic = """
            if self.skills:
                matches = 0
                # What the job requires (from tags)
                job_required_skills = [s for s in job_skills_lower if len(s) > 1]
                
                # If LinkedIn or job has no skills, we evaluate based on how many user skills match the title
                if not job_required_skills:
                    # just see if at least one user skill is in title.
                    for skill in self.skills:
                        if skill in job_title_lower:
                            matches += 1
                    # Give it a decent baseline if it matches title well
                    score = min(100, int((matches / max(1, len(self.skills))) * 100) + 50) if matches > 0 else 0
                else:
                    # Normal Naukri job with tags
                    for req_skill in job_required_skills:
                        # Does the user have this required skill?
                        # Or does the user skill somewhat align?
                        # Actually self.skills = what user searched.
                        # Wait, what if user search IS what user HAS?
                        has_it = False
                        for user_skill in self.skills:
                            if user_skill in req_skill or req_skill in user_skill:
                                has_it = True
                                break
                        if has_it:
                            matches += 1
                    
                    score = int((matches / len(job_required_skills)) * 100)
"""

# Replace the old scoring logic
import re
text = re.sub(r'            if self\.skills:\n                matches = 0\n                for skill in self\.skills:\n                    if skill in job_skills_lower or skill in job_title_lower:\n                        matches \+= 1\n                score = int\(\(matches / len\(self\.skills\)\) \* 100\)', new_logic.strip(), text, count=1)

with open('app/job_agent.py', 'w') as f:
    f.write(text)
