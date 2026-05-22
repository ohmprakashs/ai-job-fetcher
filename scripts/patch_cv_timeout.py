import re

with open('app/cv_generator.py', 'r') as f:
    text = f.read()

# Increase the timeout just in case it is dropping
old_llm = """    llm = CustomChatAnthropic(
        model_name="claude-3-haiku-20240307", 
        temperature=0.1, 
        max_tokens=200
    )"""

new_llm = """    llm = CustomChatAnthropic(
        model_name="claude-3-haiku-20240307", 
        temperature=0.1, 
        max_tokens=200,
        timeout=30.0,
        default_request_timeout=30.0
    )"""

text = text.replace(old_llm, new_llm)

with open('app/cv_generator.py', 'w') as f:
    f.write(text)
print("Added 30s timeout to LLM extraction")
