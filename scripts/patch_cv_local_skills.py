import re

with open('app/cv_generator.py', 'r') as f:
    text = f.read()

old_func_pattern = r"def extract_skills_from_cv\(pdf_path\):.*?return \"\" # Do not fallback to random skills"

new_func = """def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path).lower()
    if not text.strip():
        print("Warning: CV text extraction returned empty string!")
        return ""
        
    # Offline keyword array fallback since the LLM network requests drop
    KNOWN_SKILLS = [
        "python", "java", "c++", "c#", "javascript", "typescript", "golang", "ruby", "rust", "php",
        "react", "angular", "vue", "svelte", "node.js", "express", "django", "flask", "fastapi", "spring",
        "sql", "mysql", "postgresql", "mongodb", "oracle", "nosql", "firebase", "cassandra", "redis",
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform", "jenkins", "ansible",
        "linux", "bash", "shell", "git", "github", "gitlab", "ci/cd", "agile", "scrum",
        "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy",
        "hadoop", "spark", "kafka", "snowflake", "airflow", "databricks"
    ]
    
    found_skills = set()
    for skill in KNOWN_SKILLS:
        # Check using word boundaries so 'java' doesn't match 'javascript'
        if re.search(r'\\b' + re.escape(skill) + r'\\b', text):
            found_skills.add(skill)
            
    print("Local Extracted Skills from CV:", list(found_skills))
    return ", ".join(list(found_skills))
"""

text = re.sub(old_func_pattern, new_func, text, flags=re.DOTALL)

with open('app/cv_generator.py', 'w') as f:
    f.write(text)

