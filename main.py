import os
import logging
import json
import hashlib
import hmac
import time
from dotenv import load_dotenv
from flask import Flask, request, jsonify, abort
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from processing_chain import MessageProcessor

# Load environment variables only in development
if os.getenv('HEROKU') != 'true':
    load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure logging for production
if os.getenv('HEROKU') == 'true':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
else:
    logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

# Environment variables
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")

# Initialize Slack client
slack_client = None
if SLACK_BOT_TOKEN:
    slack_client = WebClient(token=SLACK_BOT_TOKEN)
    logger.info("✅ Slack client initialized successfully")
else:
    logger.warning("⚠️ SLACK_BOT_TOKEN not found - Slack posting disabled")

# Initialize message processor
message_processor = None
if GROQ_API_KEY:
    try:
        message_processor = MessageProcessor(groq_api_key=GROQ_API_KEY)
        logger.info("✅ MessageProcessor initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize MessageProcessor: {e}")
else:
    logger.warning("⚠️ GROQ_API_KEY not found - Message processing disabled")


def verify_slack_request(request_obj):
    """
    Verify that the request comes from Slack using the signing secret.
    """
    if not SLACK_SIGNING_SECRET:
        logger.warning("⚠️ SLACK_SIGNING_SECRET not set - skipping verification")
        return True

    try:
        # Get the timestamp and signature from headers
        timestamp = request_obj.headers.get('X-Slack-Request-Timestamp', '')
        slack_signature = request_obj.headers.get('X-Slack-Signature', '')

        # Check if request is too old (prevent replay attacks)
        if abs(time.time() - int(timestamp)) > 60 * 5:  # 5 minutes
            logger.warning("⚠️ Request timestamp too old")
            return False

        # Create the signature base string
        request_body = request_obj.get_data(as_text=True)
        sig_basestring = f"v0:{timestamp}:{request_body}"

        # Create the expected signature
        expected_signature = 'v0=' + hmac.new(
            SLACK_SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        # Compare signatures
        if hmac.compare_digest(expected_signature, slack_signature):
            return True
        else:
            logger.warning("⚠️ Invalid Slack signature")
            return False

    except Exception as e:
        logger.error(f"❌ Error verifying Slack request: {e}")
        return False


def format_extraction_message(extraction_result, original_message, user, channel):
    """
    Format extraction results for Slack posting with proper markdown.
    """
    if extraction_result.get('error'):
        return f"❌ **Extraction Error**: {extraction_result['error']}"

    # Build the message
    message_parts = [
        "🔍 **Content Analysis Results**",
        f"👤 **User**: <@{user}>",
        f"📍 **Channel**: <#{channel}>",
        f"📝 **Original Message**: _{original_message[:150]}{'...' if len(original_message) > 150 else ''}_",
        ""
    ]

    # Category emojis
    emoji_map = {
        "Decisions": "⚡",
        "ToDos": "📋",
        "SOPs": "📖",
        "Facts": "💡"
    }

    # Track if we found any categories
    categories_found = False

    # Format each category
    for category, items in extraction_result.items():
        if category == 'error' or not items or not isinstance(items, list):
            continue

        categories_found = True
        emoji = emoji_map.get(category, "📌")
        message_parts.append(f"{emoji} **{category.upper()}:**")

        # Show up to 3 items per category
        for i, item in enumerate(items[:3]):
            if isinstance(item, dict):
                text = item.get('text', '').strip()[:200]
                reason = item.get('reason', '').strip()[:150]

                if text:
                    message_parts.append(f"  • {text}")
                    if reason:
                        message_parts.append(f"    _{reason}_")

        # Show count if more items exist
        if len(items) > 3:
            message_parts.append(f"  _... and {len(items) - 3} more {category.lower()}_")

        message_parts.append("")

    # If no categories found
    if not categories_found:
        message_parts.extend([
            "📝 **Analysis Result**: No specific decisions, todos, SOPs, or facts detected in this message.",
            "_The message may be conversational or contain general information._"
        ])

    return "\n".join(message_parts)


def post_to_target_channel(message_text):
    """
    Post formatted message to the target Slack channel.
    """
    if not slack_client:
        logger.error("❌ Slack client not initialized")
        return None

    if not TARGET_CHANNEL_ID:
        logger.error("❌ TARGET_CHANNEL_ID not set")
        return None

    try:
        response = slack_client.chat_postMessage(
            channel=TARGET_CHANNEL_ID,
            text=message_text,
            parse="full",
            unfurl_links=False,
            unfurl_media=False
        )
        logger.info(f"✅ Successfully posted analysis to channel {TARGET_CHANNEL_ID}")
        return response

    except SlackApiError as e:
        logger.error(f"❌ Failed to post to Slack channel: {e.response['error']}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error posting to Slack: {e}")
        return None


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Heroku and monitoring."""
    status = {
        'status': 'healthy',
        'services': {
            'slack_client': slack_client is not None,
            'message_processor': message_processor is not None,
            'target_channel_set': TARGET_CHANNEL_ID is not None
        }
    }

    logger.info("Health check requested")
    return jsonify(status), 200


@app.route('/status', methods=['GET'])
def status():
    """Detailed status endpoint for debugging."""
    env_status = {
        'SLACK_BOT_TOKEN': 'SET' if SLACK_BOT_TOKEN else 'MISSING',
        'SLACK_SIGNING_SECRET': 'SET' if SLACK_SIGNING_SECRET else 'MISSING',
        'GROQ_API_KEY': 'SET' if GROQ_API_KEY else 'MISSING',
        'TARGET_CHANNEL_ID': 'SET' if TARGET_CHANNEL_ID else 'MISSING',
        'HEROKU': os.getenv('HEROKU', 'false')
    }

    return jsonify({
        'app_status': 'running',
        'environment_variables': env_status,
        'services_initialized': {
            'slack_client': slack_client is not None,
            'message_processor': message_processor is not None
        }
    }), 200


@app.route('/slack/events', methods=['POST'])
def slack_events():
    """
    Handle Slack event subscriptions.
    """
    logger.info("📨 Received Slack event")

    # Verify request signature
    if not verify_slack_request(request):
        logger.warning("❌ Failed to verify Slack request signature")
        abort(400, 'Could not verify Slack request signature')

    # Parse request data
    try:
        data = request.get_json()
        if not data:
            logger.error("❌ No JSON data in request")
            return jsonify({'error': 'No data provided'}), 400

    except Exception as e:
        logger.error(f"❌ Error parsing JSON data: {e}")
        return jsonify({'error': 'Invalid JSON'}), 400

    # Handle URL verification challenge
    if "challenge" in data:
        challenge = data['challenge']
        logger.info(f"🔐 Responding to Slack URL verification challenge")
        return jsonify({"challenge": challenge})

    # Handle events
    event = data.get('event', {})
    event_type = event.get('type')

    if event_type == "message":
        return handle_message_event(event, data)
    elif event_type == "app_mention":
        return handle_mention_event(event, data)
    else:
        logger.info(f"📝 Ignoring event type: {event_type}")
        return jsonify({'status': 'ignored'})


def handle_message_event(event, full_data):
    """
    Process regular message events and extract content categories.
    """
    # Extract event data
    text = event.get('text', '').strip()
    user = event.get('user', 'unknown')
    channel = event.get('channel', 'unknown')
    bot_id = event.get('bot_id')
    subtype = event.get('subtype')

    # Skip bot messages and system messages
    if bot_id or subtype:
        logger.info(f"⏭️ Skipping bot/system message (bot_id: {bot_id}, subtype: {subtype})")
        return jsonify({'status': 'skipped_bot_message'})

    # Skip empty or very short messages
    if not text or len(text.strip()) < 10:
        logger.info(f"⏭️ Skipping short message: '{text[:20]}...'")
        return jsonify({'status': 'skipped_short_message'})

    logger.info(f"🔍 Processing message from user {user} in channel {channel}")
    logger.debug(f"Message content: {text[:100]}...")

    # Check if services are available
    if not message_processor:
        logger.error("❌ MessageProcessor not initialized")
        return jsonify({'status': 'error', 'error': 'Service unavailable'}), 503

    try:
        # Extract categories using AI
        logger.info("🧠 Running content extraction...")
        extraction_result = message_processor.extract_categories(text)

        logger.info(f"✅ Extraction completed with {len(extraction_result)} categories")
        logger.debug(f"Extraction result: {extraction_result}")

        # Format and post results to target channel
        if slack_client and TARGET_CHANNEL_ID:
            formatted_message = format_extraction_message(
                extraction_result, text, user, channel
            )

            post_result = post_to_target_channel(formatted_message)

            return jsonify({
                'status': 'success',
                'extraction_categories': len([k for k, v in extraction_result.items()
                                              if k != 'error' and isinstance(v, list) and v]),
                'posted_to_channel': post_result is not None,
                'target_channel': TARGET_CHANNEL_ID
            })
        else:
            logger.warning("⚠️ Slack posting disabled - missing client or target channel")
            return jsonify({
                'status': 'success',
                'extraction_categories': len(extraction_result),
                'posted_to_channel': False,
                'extraction_result': extraction_result
            })

    except Exception as e:
        logger.error(f"❌ Error processing message: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'message': 'Failed to process message'
        }), 500


def handle_mention_event(event, full_data):
    """
    Handle direct mentions of the bot.
    """
    text = event.get('text', '')
    user = event.get('user', 'unknown')
    channel = event.get('channel', 'unknown')

    logger.info(f"👋 Bot mentioned by {user} in {channel}")

    # Respond to mention (optional feature)
    try:
        if slack_client:
            response_text = f"👋 Hi <@{user}>! I'm analyzing messages in this workspace and posting categorized insights to <#{TARGET_CHANNEL_ID}>. Just keep chatting normally!"

            slack_client.chat_postMessage(
                channel=channel,
                text=response_text,
                thread_ts=event.get('ts')  # Reply in thread
            )

        return jsonify({'status': 'mention_handled'})

    except Exception as e:
        logger.error(f"❌ Error handling mention: {e}")
        return jsonify({'status': 'error', 'error': str(e)})


@app.route('/slack/interactive', methods=['POST'])
def slack_interactive():
    """
    Handle Slack interactive components (buttons, modals, etc.).
    """
    logger.info("🎛️ Received Slack interactive component")

    if not verify_slack_request(request):
        abort(400, 'Could not verify Slack request signature')

    # Parse the payload
    try:
        payload = json.loads(request.form.get('payload', '{}'))
        callback_id = payload.get('callback_id')

        logger.info(f"Interactive component: {callback_id}")

        # Handle different interactive components here
        return jsonify({'status': 'interactive_handled'})

    except Exception as e:
        logger.error(f"❌ Error handling interactive component: {e}")
        return jsonify({'status': 'error'})


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    logger.warning(f"404 - Path not found: {request.path}")
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    logger.error(f"500 - Internal server error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(400)
def bad_request(e):
    """Handle 400 errors."""
    logger.warning(f"400 - Bad request: {str(e)}")
    return jsonify({'error': 'Bad request'}), 400


# Production WSGI application object for Gunicorn
application = app

if __name__ == "__main__":
    # This runs only in development (python main.py)
    port = int(os.getenv("PORT", 5000))
    debug_mode = os.getenv('HEROKU') != 'true'

    logger.info(f"🚀 Starting Flask app on port {port} (debug={debug_mode})")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )