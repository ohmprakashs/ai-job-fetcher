import re

with open('app/ui.py', 'r') as f:
    text = f.read()

# We need to change the logic so that if a file is uploaded, we EXTRACT SKILLS, but we DO NOT instantly search for jobs using them, because we want the user to see the skills first in the text box.
old_logic = """        if resume_file and resume_file.filename:
            global _BASE_DIR
            resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
            resume_file.save(resume_path)
            
            # Extract skills via LLM
            extracted_skills_str = extract_skills_from_cv(resume_path)
            if extracted_skills_str:
                skills = [s.strip() for s in extracted_skills_str.split(',') if s.strip()]
        location_filter = request.form.get('location', '').strip().lower()"""

new_logic = """        if resume_file and resume_file.filename:
            global _BASE_DIR
            resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
            resume_file.save(resume_path)
            
            # Extract skills via LLM
            extracted_skills_str = extract_skills_from_cv(resume_path)
            if extracted_skills_str:
                skills = [s.strip() for s in extracted_skills_str.split(',') if s.strip()]
                
            # If the user just uploaded a resume, we return immediately to show them the extracted skills in the UI
            # without triggering the full long 30-second job scrape automatically!
            has_resume = True
            return render_template(
                'index.html',
                skills=skills,
                jobs=[],
                summary={},
                common_jobs=[],
                location_filter=request.form.get('location', '').strip().lower(),
                designation_filter=request.form.get('designation', '').strip().lower(),
                experience_years=None,
                posted_within_days=None,
                did_submit=False,
                has_resume=has_resume,
            )

        location_filter = request.form.get('location', '').strip().lower()"""

text = text.replace(old_logic, new_logic)

with open('app/ui.py', 'w') as f:
    f.write(text)

