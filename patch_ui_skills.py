import re

with open('app/ui.py', 'r') as f:
    text = f.read()

# Make sure we import extract_skills_from_cv
if "from cv_generator import build_tailored_pdf" in text and "extract_skills_from_cv" not in text:
    text = text.replace("from cv_generator import build_tailored_pdf", "from cv_generator import build_tailored_pdf, extract_skills_from_cv")

# Replace the upload block to parse skills
old_code = """        # Handle resume upload
        resume_file = request.files.get('resume')
        if resume_file and resume_file.filename:
            global _BASE_DIR
            resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
            resume_file.save(resume_path)
            
        skills = [s.strip().lower() for s in request.form.get('skills', '').split(',') if s.strip()]"""

new_code = """        # Handle resume upload
        resume_file = request.files.get('resume')
        skills = [s.strip().lower() for s in request.form.get('skills', '').split(',') if s.strip()]
        
        if resume_file and resume_file.filename:
            global _BASE_DIR
            resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
            resume_file.save(resume_path)
            
            # Extract skills via LLM
            extracted_skills_str = extract_skills_from_cv(resume_path)
            if extracted_skills_str:
                skills = [s.strip() for s in extracted_skills_str.split(',') if s.strip()]"""

text = text.replace(old_code, new_code)

with open('app/ui.py', 'w') as f:
    f.write(text)

