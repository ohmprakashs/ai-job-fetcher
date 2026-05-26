from app.job_agent import JobAIAgent

agent = JobAIAgent(["java", "spring boot", "microservices", "docker"], designation="Java")
agent.fetch_and_summarize()
print([job['title'] for job in agent.get_jobs()])
