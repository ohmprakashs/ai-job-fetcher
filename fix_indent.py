with open('app/job_agent.py', 'r') as f:
    text = f.read()

text = text.replace('\nif self.skills:', '\n            if self.skills:')

with open('app/job_agent.py', 'w') as f:
    f.write(text)

