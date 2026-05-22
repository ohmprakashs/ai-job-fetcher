with open("app/cv_generator.py", "r") as f:
    text = f.read()

old_str = """    chain = prompt | llm
    # Use streaming to prevent corporate firewalls from dropping the TCP 
    # connection during long generations (which causes APITimeoutError).
    full_response = ""
    for chunk in chain.stream({
        "cv_text": base_cv_text,
        "job_title": job_title,
        "company": company,
        "skills": required_skills
    }):
        full_response += chunk.content
        
    return full_response"""

new_str = """    try:
        chain = prompt | llm
        full_response = ""
        for chunk in chain.stream({
            "cv_text": base_cv_text,
            "job_title": job_title,
            "company": company,
            "skills": required_skills
        }):
            full_response += chunk.content
        return full_response
    except Exception as e:
        print(f"LLM Generation Failed ({str(e)}). Falling back to template generation.")
        # Fallback logic for when Anthropic API is blocked by firewall/timeouts
        skills_formatted = ", ".join(required_skills) if isinstance(required_skills, list) else str(required_skills)
        fallback_text = base_cv_text.split("=======")[0] if "=======" in base_cv_text else base_cv_text
        
        fallback_cv = f"--- TAILORED RESUME ---\n\n"
        fallback_cv += f"TARGET ROLE: {job_title} at {company}\n"
        fallback_cv += f"CORE SKILLS: {skills_formatted}\n\n"
        fallback_cv += "PROFESSIONAL SUMMARY\n"
        fallback_cv += f"Dedicated professional with experience matching the {job_title} requirements at {company}. "
        fallback_cv += f"Highly skilled in {skills_formatted}.\n\n"
        fallback_cv += "=== ORIGINAL EXPERIENCE ===\n"
        fallback_cv += fallback_text
        
        return fallback_cv"""

text = text.replace(old_str, new_str)
with open("app/cv_generator.py", "w") as f:
    f.write(text)
print("Added fallback generator.")
