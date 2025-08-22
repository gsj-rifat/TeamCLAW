import os
import logging
import json
from dotenv import load_dotenv
from flask import Flask, request, jsonify, abort
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from processing_chain import MessageProcessor

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")

# Initialize Slack client
slack_client = WebClient(token=SLACK_BOT_TOKEN)


def verify_slack_request(req):
    """Verify Slack request signature"""
    # Implementation remains the same as before
    return True


def format_extraction_message(extraction_result, original_message, user, channel):
    """Format extraction results for Slack posting"""
    if extraction_result.get('error'):
        return f"❌ **Extraction Error**: {extraction_result['error']}"

    message_parts = [
        f"🔍 **Content Analysis from <#{channel}>**",
        f"👤 **Original by**: <@{user}>",
        f"📝 **Original**: _{original_message[:100]}..._",
        ""
    ]

    # Format each category
    for category, items in extraction_result.items():
        if items and isinstance(items, list):
            emoji_map = {
                "Decisions": "⚡",
                "ToDos": "📋",
                "SOPs": "📖",
                "Facts": "💡"
            }
            emoji = emoji_map.get(category, "📌")
            message_parts.append(f"{emoji} **{category}:**")

            for item in items[:3]:  # Limit to 3 items per category
                text = item.get('text', '')[:150]
                reason = item.get('reason', '')[:100]
                message_parts.append(f"  • {text}")
                message_parts.append(f"    _Reason: {reason}_")

            if len(items) > 3:
                message_parts.append(f"  ... and {len(items) - 3} more items")
            message_parts.append("")

    return "\n".join(message_parts)


def post_to_channel(message_text):
    """Post formatted message to target channel"""
    try:
        response = slack_client.chat_postMessage(
            channel=TARGET_CHANNEL_ID,
            text=message_text,
            parse="full"
        )
        logger.info(f"✅ Posted to channel {TARGET_CHANNEL_ID}")
        return response
    except SlackApiError as e:
        logger.error(f"❌ Failed to post to Slack: {e.response['error']}")
        return None


@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200


@app.route('/slack/events', methods=['POST'])
def slack_events():
    if not verify_slack_request(request):
        abort(400, 'Could not verify Slack request signature')

    data = request.get_json()

    # Handle challenge verification
    if "challenge" in data:
        return jsonify({"challenge": data['challenge']})

    # Handle message events
    event = data.get('event', {})
    if event.get('type') == "message" and not event.get('bot_id'):  # Ignore bot messages
        return handle_message_event(event, data)

    return jsonify({'status': 'ignored'})


def handle_message_event(event, full_data):
    """Process message and post extraction to target channel"""
    text = event.get('text', '')
    user = event.get('user', 'unknown')
    channel = event.get('channel', 'unknown')

    # Skip empty messages or messages from bots
    if not text.strip() or len(text) < 10:
        return jsonify({'status': 'skipped_short_message'})

    logger.info(f"📨 Processing message from {user} in {channel}")

    try:
        # Initialize processor
        processor = MessageProcessor(groq_api_key=GROQ_API_KEY)

        # Extract categories
        extraction_result = processor.extract_categories(text)
        logger.info(f"🧠 Extraction completed: {len(extraction_result)} categories")

        # Format and post results
        formatted_message = format_extraction_message(
            extraction_result, text, user, channel
        )

        # Post to target channel
        slack_response = post_to_channel(formatted_message)

        return jsonify({
            'status': 'success',
            'extraction_categories': len(extraction_result),
            'posted_to_channel': bool(slack_response)
        })

    except Exception as e:
        logger.error(f"❌ Error processing message: {str(e)}")
        return jsonify({'status': 'error', 'error': str(e)})


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)