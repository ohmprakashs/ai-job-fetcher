with open("app/cv_generator.py", "r") as f:
    text = f.read()

import_str = "from langchain_core.prompts import PromptTemplate"
new_import_str = "from langchain_core.prompts import PromptTemplate\nfrom jd_scraper import scrape_jd_text"

text = text.replace(import_str, new_import_str)

old_def = """def generate_tailored_cv(base_cv_text, job_title, company, required_skills):"""
new_def = """def generate_tailored_cv(base_cv_text, job_title, company, required_skills, real_jd_text=""):"""
text = text.replace(old_def, new_def)

old_template = """        Required Skills: {skills}

        Base Resume:"""
new_template = """        Required Skills: {skills}
        Job Description Text: {jd_text}

        Base Resume:"""
text = text.replace(old_template, new_template)

old_prompt_vars = """input_variables=["cv_text", "job_title", "company", "skills"],"""
new_prompt_vars = """input_variables=["cv_text", "job_title", "company", "skills", "jd_text"],"""
text = text.replace(old_prompt_vars, new_prompt_vars)

old_invoke = """        for chunk in chain.stream({
            "cv_text": base_cv_text,
            "job_title": job_title,
            "company": company,
            "skills": required_skills
        }):"""
new_invoke = """        for chunk in chain.stream({
            "cv_text": base_cv_text,
            "job_title": job_title,
            "company": company,
            "skills": required_skills,
            "jd_text": real_jd_text
        }):"""
text = text.replace(old_invoke, new_invoke)

old_build = """    title = job_dict.get('title', 'Software Engineer')
    company = job_dict.get('company', 'Unknown')
    skills = job_dict.get('skills', '')
    
    tailored_text = generate_tailored_cv(base_text, title, company, skills)"""
new_build = """    title = job_dict.get('title', 'Software Engineer')
    company = job_dict.get('company', 'Unknown')
    url = job_dict.get('url', '')
    source = job_dict.get('source', '')
    skills = job_dict.get('skills', '')
    
    # Try to grab the real JD dynamically:
    real_jd = scrape_jd_text(url, source)
    
    tailored_text = generate_tailored_cv(base_text, title, company, skills, real_jd)"""
text = text.replace(old_build, new_build)

with open("app/cv_generator.py", "w") as f:
    f.write(text)

print("Updated cv_generator to use live JD scraping!")
