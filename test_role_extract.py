import re
from app.cv_generator import extract_text_from_pdf

def extract_role_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        return ""
    
    # Common roles to look for
    KNOWN_ROLES = [
        "Software Engineer", "Backend Developer", "Frontend Developer", "Full Stack Developer",
        "Data Scientist", "Data Engineer", "Machine Learning Engineer", "DevOps Engineer",
        "Cloud Engineer", "System Administrator", "Database Administrator", "Site Reliability Engineer",
        "Python Developer", "Java Developer", "Web Developer", "UI/UX Developer",
        "Product Manager", "Project Manager", "Scrum Master", "Business Analyst"
    ]
    
    found_roles = []
    # Search the first few lines / early part of the resume heavily
    cv_head = text[:1000].lower()
    
    for role in KNOWN_ROLES:
        escaped_role = re.escape(role.lower())
        if re.search(r'(?<![a-z0-9])' + escaped_role + r'(?![a-z0-9])', cv_head):
            found_roles.append(role)
            
    if found_roles:
        # Return the longest role found (e.g. "Senior Python Developer" if we matched "Python Developer")
        return found_roles[0] # or just the first matched
    return ""

print("Found Role:", extract_role_from_cv("sample_cv.pdf"))
