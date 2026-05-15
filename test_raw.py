import anthropic
import os

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

try:
    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=10,
        messages=[
            {"role": "user", "content": "Hello, Claude"}
        ]
    )
    print(message.content)
except Exception as e:
    print("ERROR:", e)
