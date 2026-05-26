with open("app/cv_generator.py", "r") as f:
    text = f.read()

new_func = """
def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path).lower()
    if not text.strip():
        print("Warning: CV text extraction returned empty string!")
        return ""
        
    KNOWN_SKILLS = set([
        "python", "java", "c++", "c#", "javascript", "typescript", "golang", "ruby", "rust", "php",
        "react", "angular", "vue", "svelte", "node.js", "express", "django", "flask", "fastapi", "spring",
        "sql", "mysql", "postgresql", "mongodb", "oracle", "nosql", "firebase", "cassandra", "redis", "sqlite",
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform", "jenkins", "ansible",
        "linux", "bash", "shell", "git", "github", "gitlab", "ci/cd", "agile", "scrum",
        "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy",
        "hadoop", "spark", "kafka", "snowflake", "airflow", "databricks", "prometheus", "grafana", "servicenow"
    ])
    
    # Dynamically pull all known skills from the DB to make it infinitely smarter!
    try:
        import sqlite3
        conn = sqlite3.connect("jobs.db")
        c = conn.cursor()
        c.execute("SELECT DISTINCT skills FROM jobs WHERE skills IS NOT NULL AND skills != ''")
        for row in c.fetchall():
            for s in row[0].split(','):
                s = s.strip().lower()
                if len(s) > 2:  # Avoid matching single letters or 2 letter words casually
                    KNOWN_SKILLS.add(s)
        conn.close()
    except Exception as e:
        print("Could not fetch extra skills from DB:", e)
    
    found_skills = set()
    # Sort skills by length descending, so 'google cloud' matches before 'google' or 'cloud'
    for skill in sorted(list(KNOWN_SKILLS), key=len, reverse=True):
        import re
        # Use regex to match whole words/phrases to prevent 'c' matching inside 'machine'
        escaped_skill = re.escape(skill)
        if re.search(r'(?<![a-z])' + escaped_skill + r'(?![a-z])', text):
            found_skills.add(skill)
            
    print("Local Extracted Skills from CV:", list(found_skills))
    return ", ".join(list(found_skills))
"""

import re
text = re.sub(r'def extract_skills_from_cv\(pdf_path\):[\s\S]+$', new_func.strip(), text)

with open("app/cv_generator.py", "w") as f:
    f.write(text)

print("Patched cv_generator.py")
