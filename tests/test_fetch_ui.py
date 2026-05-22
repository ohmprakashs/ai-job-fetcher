import sys
sys.path.append('app')
import app.job_fetcher
app.job_fetcher.fetch_jobs = lambda *args, **kwargs: []
from app.job_agent import JobAIAgent

agent = JobAIAgent(skills=["java"])
summary = agent.fetch_and_summarize()
print("Total jobs for java:", len(agent.get_jobs()))

agent2 = JobAIAgent(skills=[])
summary = agent2.fetch_and_summarize()
print("Total jobs for empty:", len(agent2.get_jobs()))

