import sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
from ai_matcher import generate_ai_match_report

job = {
    "title": "Software Engineer",
    "skills": "python,React,Sql,git",
    "url": "https://linkedin.com/123"
}
job['skills'] = job['skills'].split(',') 
print("Testing Mock NLP...")
print(generate_ai_match_report("sample_cv.pdf", job))
