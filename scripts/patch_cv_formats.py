import re

with open("app/cv_generator.py", "r") as f:
    text = f.read()

new_cv_gen = """def format_offline_cv(base_cv_text, job_title, company, required_skills, real_jd_text):
    import re
    skills_list = required_skills if isinstance(required_skills, list) else []
    if isinstance(required_skills, str) and required_skills:
        skills_list = [s.strip() for s in required_skills.split(",")]
        
    if real_jd_text and not skills_list:
        common_skills = ["python", "java", "c++", "c#", "aws", "docker", "kubernetes", "react", "angular", "node.js", "sql", "nosql", "agile", "flask", "django", "machine learning", "data science", "javascript", "typescript", "git", "ci/cd", "azure", "gcp"]
        jd_lower = real_jd_text.lower()
        skills_list = [s for s in common_skills if s in jd_lower]

    skills_str = ", ".join(list(dict.fromkeys(skills_list))).title()
    
    lines = [line.strip() for line in base_cv_text.split('\\n') if line.strip()]
    name = lines[0] if lines else "Candidate Profile"
    
    cv_text = f"{name}\\n"
    cv_text += f"{job_title.upper()} | TARGETING: {company.upper()}\\n"
    cv_text += "---\\n"
    cv_text += "PROFESSIONAL SUMMARY\\n"
    cv_text += f"Results-driven professional with experience aligned to the {job_title} role at {company}. "
    if skills_str:
        cv_text += f"Possess strong foundational expertise in core requirements including {skills_str}. "
    cv_text += "Proven ability to leverage analytical and technical competencies to tackle complex problems and deliver high-quality solutions efficiently.\\n\\n"
    
    if skills_str:
        cv_text += "TARGET SKILLS & COMPETENCIES\\n"
        skill_tokens = [s.strip() for s in skills_str.split(',')]
        # Split skills into rows of 4
        chunked = [", ".join(skill_tokens[i:i+4]) for i in range(0, len(skill_tokens), 4)]
        for c in chunked:
             cv_text += f"- {c}\\n"
        cv_text += "\\n"
        
    cv_text += "EXPERIENCE & EDUCATION\\n"
    for line in lines[1:]:
         if line.lower() in ["experience:", "education:"] or "=====" in line:
             cv_text += f"\\n{line.upper()}\\n"
         elif bool(re.match(r'^[-•*]', line)):
             cv_text += f"- {line[1:].strip()}\\n"
         else:
             cv_text += f"{line}\\n"
             
    return cv_text

def generate_tailored_cv(base_cv_text, job_title, company, required_skills, real_jd_text=""):
    llm = CustomChatAnthropic(
        model_name="claude-3-haiku-20240307", 
        temperature=0.7, 
        max_retries=1,
        default_request_timeout=5.0,
        timeout=5.0
    )
    prompt = PromptTemplate(
        input_variables=["cv_text", "job_title", "company", "skills", "jd_text"],
        template='''You are an expert ATS resume writer. Output ONLY the formatted resume text. Do NOT wrap in code blocks.
        Job Title: {job_title}
        Company: {company}
        Skills: {skills}
        Job Description: {jd_text}
        
        Base Resume:
        {cv_text}
        '''
    )
    try:
        chain = prompt | llm
        full_response = ""
        for chunk in chain.stream({
            "cv_text": base_cv_text,
            "job_title": job_title,
            "company": company,
            "skills": required_skills,
            "jd_text": real_jd_text
        }):
            full_response += chunk.content
            
        print("✅ LLM returned correctly.")
        return full_response
    except Exception as e:
        print(f"⚠️ LLM Blocked by Network ({str(e)}). Using high-quality offline ATS template formatting...")
        return format_offline_cv(base_cv_text, job_title, company, required_skills, real_jd_text)

def create_pdf(text, output_path):
    text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    
    lines = text.split('\\n')
    
    if lines:
        pdf.set_font("Helvetica", 'B', 20)
        pdf.cell(0, 10, lines[0].strip(), ln=True, align="C")
        lines = lines[1:]
        
    for line in lines:
        line_str = line.strip()
        if not line_str:
            pdf.ln(3)
            continue
            
        if line_str == "---":
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(3)
            continue
            
        if line_str.isupper() and len(line_str) > 4 and "|" not in line_str:
            pdf.ln(4)
            pdf.set_font("Helvetica", 'B', 12)
            # Use Professional Dark Blue for Headers
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 6, line_str, ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
        elif "|" in line_str and "TARGETING" in line_str:
            pdf.set_font("Helvetica", 'I', 11)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 6, line_str, ln=True, align="C")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)
        elif line_str.startswith("-") or line_str.startswith("•") or line_str.startswith("*"):
            pdf.set_font("Helvetica", '', 11)
            pdf.set_x(20)
            pdf.multi_cell(0, 5, chr(149) + " " + line_str[1:].strip())
            pdf.set_x(15)
        else:
            pdf.set_font("Helvetica", '', 11)
            pdf.multi_cell(0, 5, line_str)
            
    pdf.output(output_path)
"""

start_idx = text.find("def generate_tailored_cv")
end_idx = text.find("def build_tailored_pdf")

if start_idx != -1 and end_idx != -1:
    new_text = text[:start_idx] + new_cv_gen + "\n" + text[end_idx:]
    with open("app/cv_generator.py", "w") as f:
        f.write(new_text)
    print("Patched cv_generator formatting successfully!")
else:
    print("Indices not found!")
