import re

with open('app/ui.py', 'r') as f:
    text = f.read()

import os
# We need to save the uploaded file if it exists.
new_index_logic = """    if request.method == 'POST':
        did_submit = True
        
        # Handle resume upload
        resume_file = request.files.get('resume')
        if resume_file and resume_file.filename:
            global _BASE_DIR
            resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
            resume_file.save(resume_path)
            
        skills = [s.strip().lower() for s in request.form.get('skills', '').split(',') if s.strip()]"""

text = text.replace("    if request.method == 'POST':\n        did_submit = True\n        skills = [s.strip().lower() for s in request.form.get('skills', '').split(',') if s.strip()]", new_index_logic)

with open('app/ui.py', 'w') as f:
    f.write(text)
