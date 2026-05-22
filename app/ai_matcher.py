import os
import re
from cv_generator import extract_text_from_pdf

def generate_ai_match_report(cv_path: str, job_dict: dict) -> str:
    if not os.path.exists(cv_path):
        return "No CV found. Please upload a resume first."
        
    cv_text = extract_text_from_pdf(cv_path)
    if not cv_text.strip():
        return "CV appears to be empty."
        
    cv_lower = cv_text.lower()
    
    # Use skills from DB instead of fetching the URL
    job_skills = job_dict.get('skills', [])
    job_title = job_dict.get('title', 'Unknown Title')
    
    if not job_skills:
        # Fallback to extracting some keywords from title
        words = re.findall(r'\b\w+\b', job_title.lower())
        job_skills = [w for w in words if len(w) > 3]

    if not job_skills:
         return "No skills found for this job to match against."
         
    found_skills = []
    missing_skills = []
    
    for skill in set(job_skills):
        skill_clean = str(skill).strip().lower()
        if not skill_clean: continue
        # Simple substring match for the skill
        if skill_clean in cv_lower:
            found_skills.append(skill_clean)
        else:
            missing_skills.append(skill_clean)
            
    total_skills = len(found_skills) + len(missing_skills)
    
    if total_skills == 0:
        score = 0
    else:
        score = int((len(found_skills) / total_skills) * 100)
        
    # Generate a mock LLM-style paragraph
    report = f"**ATS Recruiter AI Analysis**\n\n"
    report += f"The candidate's CV has been evaluated against the role of **{job_title}**. "
    
    if score >= 75:
        report += f"This is a **strong match** with an ATS score of **{score}%**! "
    elif score >= 50:
        report += f"This is a **moderate match** with an ATS score of **{score}%**. "
    else:
        report += f"This is a **weak match** with an ATS score of **{score}%**. "
        
    if found_skills:
        report += f"The CV successfully highlights the following required skills: {', '.join(found_skills[:5])}. "
        
    if missing_skills:
        report += f"However, the candidate appears to be completely missing key requirements such as: {', '.join(missing_skills[:5])}. "
        report += "Consider tailoring the CV to include these terms if you have experience with them."
    else:
        report += "The candidate covers all the extracted key requirements perfectly."
        
    return report
