with open("app/job_fetcher.py", "r") as f:
    text = f.read()

old_fallback = """                    extracted_skills = [s for s in skills if s.lower() in (job_title + " " + card_text).lower()]
                    if not extracted_skills and skills:
                        # Fallback: if LinkedIn matched it but we don't see the word directly, just stamp it with the searched skills.
                        extracted_skills = skills.copy()"""

new_fallback = """                    extracted_skills = []
                    search_text = (job_title + " " + card_text).lower()
                    for s in skills:
                        import re
                        if re.search(r'(?<![a-z0-9])' + re.escape(s.lower()) + r'(?![a-z0-9])', search_text):
                            extracted_skills.append(s)
                            
                    # Remove the fallback that copies the user skills. We only want what is actually found."""

text = text.replace(old_fallback, new_fallback)

with open("app/job_fetcher.py", "w") as f:
    f.write(text)
