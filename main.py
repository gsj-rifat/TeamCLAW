# main.py
import os
from dotenv import load_dotenv
from slack_bot import SlackBot

# Load environment variables
load_dotenv()


def main():
    # Get API keys from environment
    groq_api_key = os.getenv('GROQ_API_KEY')  # Updated from GROK to GROQ
    slack_bot_token = os.getenv('SLACK_BOT_TOKEN')
    slack_signing_secret = os.getenv('SLACK_SIGNING_SECRET')
    slack_channel_id = os.getenv('SLACK_CHANNEL_ID')

    # Debug: Check if API key is loaded
    if not groq_api_key:
        print("ERROR: GROQ_API_KEY not found in environment variables!")
        print("Please set your GROQ API key in the .env file")
        return

    print(f"GROQ_API_KEY loaded: {groq_api_key[:10]}...")  # Show first 10 chars

    # Create bot with GROQ API key
    bot = SlackBot(
        groq_api_key=groq_api_key,  # Updated parameter name
        slack_bot_token=slack_bot_token,
        slack_signing_secret=slack_signing_secret,
        slack_channel_id=slack_channel_id
    )

    print("Starting AI Shadow Coach with GROQ API...")
    bot.start()


if __name__ == "__main__":
    main()