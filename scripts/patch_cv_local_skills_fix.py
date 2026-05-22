import re

with open('app/cv_generator.py', 'r') as f:
    text = f.read()

old_code = """def extract_skills_from_cv(pdf_path):
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
        if re.search(r' + re.escape(skill) + r', text):
            found_skills.add(skill)
            
    print("Local Extracted Skills from CV:", list(found_skills))
    return ", ".join(list(found_skills))"""

new_code = """import re

def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path).lower()
    if not text.strip():
        print("Warning: CV text extraction returned empty string!")
        return ""
        
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
        # Avoid partial word matches
        pattern = r"\\b" + re.escape(skill) + r"\\b"
        if re.search(pattern, text):
            found_skills.add(skill)
            
    print("Local Extracted Skills from CV:", list(found_skills))
    return ", ".join(list(found_skills))"""

text = text.replace(old_code, new_code)
with open('app/cv_generator.py', 'w') as f:
    f.write(text)

