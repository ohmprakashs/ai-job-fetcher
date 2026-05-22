import os
from dotenv import load_dotenv
load_dotenv()
from langchain_anthropic import ChatAnthropic

class CustomChatAnthropic(ChatAnthropic):
    model_config = {"extra": "allow"}
    @property
    def provider(self): return "anthropic"
    @property
    def model_name(self): return self.model

llm = CustomChatAnthropic(model_name="claude-3-5-sonnet-20241022", temperature=0.0)
try:
    print(llm.invoke("Hi").content)
except Exception as e:
    print("FAILED:", type(e).__name__, e)
