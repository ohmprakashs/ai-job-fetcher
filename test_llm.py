from langchain_anthropic import ChatAnthropic
class MockChatAnthropic(ChatAnthropic):
    @property
    def provider(self):
        return "anthropic"

llm = MockChatAnthropic(model_name="claude-3-5-sonnet-20241022")
print(llm.provider)
