import sys
sys.path.insert(0, './app')
from job_agent import JobAIAgent
agent = JobAIAgent(["python", "django", "aws", "docker"], designation="Backend")
agent.fetch_and_summarize()
for job in agent.get_jobs()[:3]:
    print(f"Title: {job['title']}")
    print(f"Job Skills: {job['skills']}")
    print(f"Matched Skills: {job.get('matched_skills')}")
    print(f"Match Score: {job.get('match_score')}%")
    print("---")
