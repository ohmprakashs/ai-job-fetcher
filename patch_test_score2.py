import sys
sys.path.insert(0, './app')
from job_agent import JobAIAgent

print("Testing AI Agent...")
agent = JobAIAgent(["java", "spring boot", "microservices", "docker", "aws", "sql", "hibernate", "git"], designation="Java Developer")
agent.fetch_and_summarize()
print(f"Total returned jobs: {len(agent.get_jobs())}")
