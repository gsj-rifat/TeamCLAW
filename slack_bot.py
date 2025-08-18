# slack_bot.py
from processing_chain import MessageProcessor


class SlackBot:
    def __init__(self, groq_api_key, slack_bot_token, slack_signing_secret, slack_channel_id):
        # Debug: Verify API key is received
        print(f"SlackBot received GROQ API key: {groq_api_key[:10] if groq_api_key else 'None'}...")

        if not groq_api_key:
            raise ValueError("groq_api_key is required but not provided")

        # Initialize message processor with GROQ
        self.processor = MessageProcessor(groq_api_key)  # Pass GROQ API key

        # Store Slack configuration
        self.bot_token = slack_bot_token
        self.signing_secret = slack_signing_secret
        self.channel_id = slack_channel_id

        print("SlackBot initialized with GROQ LLM")

        # Print model information
        model_info = self.processor.llm.get_model_info()
        print(f"Using model best for: {model_info.get('best_for', 'General use')}")

    def start(self):
        """Start the Slack bot"""
        print("AI Shadow Coach is now running with GROQ API!")
        # Your existing Slack bot logic here...