with open('app/ui.py', 'r') as f:
    content = f.read()

import re
new_content = re.sub(
    r"report = generate_ai_match_report\(resume_path, job\['url'\], job\['title'\]\)",
    r"report = generate_ai_match_report(resume_path, job)",
    content
)

with open('app/ui.py', 'w') as f:
    f.write(new_content)

print("Patched app/ui.py!")
