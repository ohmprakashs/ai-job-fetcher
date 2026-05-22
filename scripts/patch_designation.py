import re

with open('app/job_agent.py', 'r') as f:
    text = f.read()

# Fix designation filtering to be word-based, not exact phrase
old_desig = """            # Check designation strictly against Job Title
            if self.designation:
                job_title = str(job.get("title", "")).lower()
                if self.designation not in job_title:
                    continue"""

new_desig = """            # Check designation flexibly against Job Title
            if self.designation:
                job_title = str(job.get("title", "")).lower()
                desig_parts = self.designation.replace(',', ' ').split()
                # Ensure all words from designation are found in the title
                if not all(part in job_title for part in desig_parts):
                    continue"""

text = text.replace(old_desig, new_desig)

# Update bonus score logic too
text = text.replace('if self.designation and self.designation in job_title_lower:', 'if self.designation and all(p in job_title_lower for p in self.designation.replace(",", " ").split()):')

with open('app/job_agent.py', 'w') as f:
    f.write(text)


with open('app/job_fetcher.py', 'r') as f:
    text = f.read()

# Replace designation override
old_keyword = "keyword = designation if designation else _build_search_keyword(skills)"
new_keyword = "keyword = f'{designation} {_build_search_keyword(skills)}'.strip()"
text = text.replace(old_keyword, new_keyword)

with open('app/job_fetcher.py', 'w') as f:
    f.write(text)
