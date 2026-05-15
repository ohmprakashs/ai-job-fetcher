import httpx
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")

try:
    with httpx.Client(timeout=10.0, verify=False) as client:
        r = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": "claude-3-haiku-20240307",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "hi"}]
            }
        )
        print("Status:", r.status_code)
        print("Text:", r.text)
except Exception as e:
    print("Error:", type(e).__name__, e)
