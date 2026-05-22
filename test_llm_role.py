import sys
sys.path.insert(0, './app')
from cv_generator import extract_text_from_pdf, CustomChatAnthropic
from langchain_core.prompts import PromptTemplate

def test():
    text = extract_text_from_pdf("sample_cv.pdf")
    if not text:
        print("No text")
        return
    llm = CustomChatAnthropic(
        model_name="claude-3-haiku-20240307", 
        temperature=0, 
        max_retries=1,
        default_request_timeout=5.0,
        timeout=5.0
    )
    prompt = PromptTemplate(
        input_variables=["cv_text"],
        template='''You are an expert technical recruiter. Based on the following resume, identify the single most appropriate primary job role or designation this candidate is targeting or is qualified for (e.g., Software Engineer, Backend Developer, Data Scientist). Do NOT output sentences. Output ONLY the job title, nothing else.
Resume:
{cv_text}'''
    )
    try:
        chain = prompt | llm
        resp = chain.invoke({"cv_text": text[:2000]})
        print("Role:", resp.content)
    except Exception as e:
        print("Error:", e)

test()
