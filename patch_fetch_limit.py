with open("app/job_fetcher.py", "r") as f:
    text = f.read()

import re

old_build = """def _build_search_keyword(skills):
    normalized = _normalize_skills(skills)
    if not normalized:
        return "python"
    return " ".join(normalized)"""

new_build = """def _build_search_keyword(skills):
    normalized = _normalize_skills(skills)
    if not normalized:
        return ""
    # Passing 20 keywords to job portals returns 0 results or garbage.
    # Take at most top 2 skills for the search query to keep it broad enough.
    return " ".join(normalized[:2])"""

text = text.replace(old_build, new_build)

with open("app/job_fetcher.py", "w") as f:
    f.write(text)
print("done")
