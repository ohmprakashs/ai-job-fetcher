import re

with open('app/cv_generator.py', 'r') as f:
    text = f.read()

old_func_pattern = r"def extract_skills_from_cv\(pdf_path\):.*?return \"python, java, sql, docker, api\" # fallback"

new_func = """def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print("Warning: CV text extraction returned empty string!")
        return ""
        
    llm = CustomChatAnthropic(
        model_name="claude-3-haiku-20240307", 
        temperature=0.1, 
        max_tokens=200
    )
    prompt = PromptTemplate(
        input_variables=["cv_text"],
        template='''You are an expert tech recruiter. Carefully read the resume below.
        
1. Extract the EXACT technical skills, programming languages, and tools explicitly mentioned.
2. Add 2-3 highly related synonymous tech skills to expand the search (e.g., if they have "React", you might add "javascript", if they have "PyTorch", add "deep learning").
3. Do NOT hallucinate random skills not implied by the resume.

Return ONLY a single comma-separated list of these skills in lowercase. No other text.

Resume:
{cv_text}'''
    )
    try:
        chain = prompt | llm
        response = chain.invoke({"cv_text": text})
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Clean up
        skills = [s.strip().lower() for s in content.split(',') if s.strip()]
        
        # Remove empty or weird strings
        skills = [s for s in skills if len(s) > 1 and " " * 4 not in s]
        print("Extracted Skills from CV:", skills)
        
        return ", ".join(skills)
    except Exception as e:
        print(f"Error extracting skills: {e}")
        return "" # Do not fallback to random skills
"""

text = re.sub(old_func_pattern, new_func, text, flags=re.DOTALL)

with open('app/cv_generator.py', 'w') as f:
    f.write(text)

print("Updated extract_skills_from_cv logic")
