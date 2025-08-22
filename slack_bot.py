import os
from processing_chain import MessageProcessor

class SlackBot:
    def __init__(self, slack_api_token=None, groq_api_key=None):
        print("🤖 Initializing SlackBot...")
        self.slack_api_token = slack_api_token or os.getenv("SLACK_API_TOKEN")
        self.processor = MessageProcessor(groq_api_key=groq_api_key or os.getenv("GROQ_API_KEY"))
        print("✅ SlackBot ready!")

    def start(self):
        # Simulate a bot startup; in a production script, this would connect to Slack RTM API or similar.
        print("🚦 SlackBot started. Listening for Slack events...")

    # Optionally allow: extraction functionality via CLI or Slack command
    def extract_transcript(self, transcript: str):
        result = self.processor.extract_categories(transcript)
        print(f"[Extraction Result]:\n{result}")
        return result