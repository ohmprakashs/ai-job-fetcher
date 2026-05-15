import re

with open('app/cv_generator.py', 'r') as f:
    text = f.read()

new_func = """
def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    llm = CustomChatAnthropic(
        model_name="claude-3-haiku-20240307", 
        temperature=0.2, 
        max_tokens=200
    )
    prompt = PromptTemplate(
        input_variables=["cv_text"],
        template='''Extract the top 10 core technical skills, programming languages, and frameworks from this resume.
Return ONLY a comma-separated list of the skill names in lowercase. No other text or explanation.

Resume:
{cv_text}'''
    )
    try:
        chain = prompt | llm
        response = chain.invoke({"cv_text": text})
        # Claude returns an AIMessage object, get content
        content = response.content if hasattr(response, 'content') else str(response)
        # clean it up just in case
        skills = [s.strip().lower() for s in content.split(',')]
        return ", ".join(skills) # return a clean comma-separated string
    except Exception as e:
        print(f"Error extracting skills: {e}")
        return "python, java, sql, docker, api" # fallback

"""

if "def extract_skills_from_cv" not in text:
    text += new_func
    with open('app/cv_generator.py', 'w') as f:
        f.write(text)

print("Patched cv_generator.py")
