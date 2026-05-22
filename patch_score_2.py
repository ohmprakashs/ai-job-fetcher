with open("app/job_agent.py", "r") as f:
    text = f.read()

import re
old_match = """                if not job_required_skills:
                    for skill in self.skills:
                        if skill in search_text:
                            matched_skills.append(skill)
                        else:
                            missing_skills.append(skill)
                else:
                    # Normal Naukri job with explicit tags
                    for user_skill in self.skills:
                        has_it = False
                        for req_skill in job_required_skills:
                            if user_skill in req_skill or req_skill in user_skill:
                                has_it = True
                                break
                        if not has_it and user_skill in search_text:
                            has_it = True
                            
                        if has_it:
                            matched_skills.append(user_skill)
                        else:
                            missing_skills.append(user_skill)"""

new_match = """                # Search text should include both the title and the job's snippet/description
                search_text = job_title_lower + " " + str(job.get("description", "")).lower() + " " + str(job.get("snippet", "")).lower()
                
                if not job_required_skills:
                    for skill in self.skills:
                        # Use word boundaries so "c" doesn't match inside "machine"
                        import re
                        if re.search(r'(?<![a-z0-9])' + re.escape(skill) + r'(?![a-z0-9])', search_text):
                            matched_skills.append(skill)
                        else:
                            missing_skills.append(skill)
                else:
                    for user_skill in self.skills:
                        has_it = False
                        for req_skill in job_required_skills:
                            if user_skill == req_skill or (len(user_skill) > 2 and user_skill in req_skill):
                                has_it = True
                                break
                        if not has_it:
                            import re
                            if re.search(r'(?<![a-z0-9])' + re.escape(user_skill) + r'(?![a-z0-9])', search_text):
                                has_it = True
                            
                        if has_it:
                            matched_skills.append(user_skill)
                        else:
                            missing_skills.append(user_skill)"""

text = text.replace(old_match, new_match)
with open("app/job_agent.py", "w") as f:
    f.write(text)
