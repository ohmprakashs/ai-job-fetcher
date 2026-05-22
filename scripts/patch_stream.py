with open("app/cv_generator.py", "r") as f:
    text = f.read()

old_str = """    chain = prompt | llm
    result = chain.invoke({
        "cv_text": base_cv_text,
        "job_title": job_title,
        "company": company,
        "skills": required_skills
    })
    return result.content"""

new_str = """    chain = prompt | llm
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

if old_str in text:
    text = text.replace(old_str, new_str)
    with open("app/cv_generator.py", "w") as f:
        f.write(text)
    print("Patched cv_generator to use streaming!")
else:
    print("Could not find the string to replace.")
