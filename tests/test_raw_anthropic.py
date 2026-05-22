import os
from dotenv import load_dotenv
load_dotenv()
import anthropic

client = anthropic.Anthropic(timeout=10.0)
try:
    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}]
    )
    print("Success!", message.content)
except Exception as e:
    print("Error:", type(e).__name__, e)
