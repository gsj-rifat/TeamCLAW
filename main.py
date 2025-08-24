import os
import json
import hashlib
import hmac
from flask import Flask, request, jsonify
from groq import Groq

app = Flask(__name__)

# Initialize Groq client
try:
    groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
    print("✅ Groq client initialized successfully")
except Exception as e:
    print(f"❌ Groq initialization error: {e}")
    groq_client = None

# Slack configuration
SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')
TARGET_CHANNEL_ID = os.getenv('TARGET_CHANNEL_ID')


def verify_slack_request(request):
    """Verify the request is from Slack"""
    if not SLACK_SIGNING_SECRET:
        return True  # Skip verification if no secret set

    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')

    if not timestamp or not signature:
        return False

    # Create expected signature
    req_body = request.get_data().decode('utf-8')
    sig_basestring = f'v0:{timestamp}:{req_body}'
    expected_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


def extract_insights_with_groq(text):
    """Extract decisions, todos, and facts using Groq"""
    try:
        prompt = f"""
Analyze the following message and extract:
1. DECISIONS - Any decisions made or conclusions reached
2. TODOS - Action items, tasks, or things to be done
3. FACTS - Key facts, metrics, or important information

Message: "{text}"

Format as JSON:
{{
  "decisions": ["decision 1", "decision 2"],
  "todos": ["todo 1", "todo 2"],
  "facts": ["fact 1", "fact 2"]
}}
"""

        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="mixtral-8x7b-32768",
            temperature=0.1,
            max_tokens=1000
        )

        result = response.choices[0].message.content.strip()

        # Parse JSON response
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"decisions": [], "todos": [], "facts": []}

    except Exception as e:
        print(f"Groq extraction error: {e}")
        return {"decisions": [], "todos": [], "facts": []}


def post_to_slack_channel(channel_id, message):
    """Post message to Slack channel"""
    import requests

    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}",
        "Content-Type": "application/json"
    }

    payload = {
        "channel": channel_id,
        "text": message,
        "username": "AI Insights Bot"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Slack post error: {e}")
        return False


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'groq_configured': bool(os.getenv('GROQ_API_KEY')),
        'slack_configured': bool(os.getenv('SLACK_BOT_TOKEN')),
        'target_channel': bool(os.getenv('TARGET_CHANNEL_ID'))
    })


@app.route('/slack/events', methods=['POST'])
def slack_events():
    # Verify request is from Slack
    if not verify_slack_request(request):
        return jsonify({'error': 'Invalid signature'}), 403

    data = request.get_json() or {}

    # Handle Slack URL verification
    if "challenge" in data:
        return jsonify({"challenge": data['challenge']})

    # Process events
    if "event" in data:
        event = data["event"]

        # Handle message events
        if event.get("type") == "message":
            # Skip bot messages and message changes
            if "bot_id" in event or "subtype" in event:
                return jsonify({'status': 'ignored_bot_message'})

            message_text = event.get("text", "")
            user_id = event.get("user", "")
            channel_id = event.get("channel", "")

            # Skip empty messages
            if not message_text.strip():
                return jsonify({'status': 'empty_message'})

            print(f"📨 Processing message from user {user_id}: {message_text[:100]}...")

            # Extract insights using Groq
            insights = extract_insights_with_groq(message_text)

            # Format results for Slack
            if any(insights.get(key) for key in ["decisions", "todos", "facts"]):
                formatted_message = "🤖 *AI Insights Extracted:*\n\n"

                if insights["decisions"]:
                    formatted_message += "⚡ *DECISIONS:*\n"
                    for decision in insights["decisions"]:
                        formatted_message += f"• {decision}\n"
                    formatted_message += "\n"

                if insights["todos"]:
                    formatted_message += "📋 *TODOS:*\n"
                    for todo in insights["todos"]:
                        formatted_message += f"• {todo}\n"
                    formatted_message += "\n"

                if insights["facts"]:
                    formatted_message += "💡 *FACTS:*\n"
                    for fact in insights["facts"]:
                        formatted_message += f"• {fact}\n"

                formatted_message += f"\n_Source: <#{channel_id}>_"

                # Post to target channel
                if TARGET_CHANNEL_ID:
                    success = post_to_slack_channel(TARGET_CHANNEL_ID, formatted_message)
                    if success:
                        print("✅ Posted insights to target channel")
                    else:
                        print("❌ Failed to post to target channel")

                return jsonify({'status': 'processed', 'insights_found': True})
            else:
                print("ℹ️ No significant insights found in message")
                return jsonify({'status': 'no_insights'})

    return jsonify({'status': 'event_ignored'})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)