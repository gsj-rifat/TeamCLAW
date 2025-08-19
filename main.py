import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Load environment variables
load_dotenv()

groq_api_key = os.getenv('GROQ_API_KEY')
slack_signing_secret = os.getenv('SLACK_SIGNING_SECRET')
slack_bot_token = os.getenv('SLACK_BOT_TOKEN')
slack_channel_id = os.getenv('SLACK_CHANNEL_ID')

# Minimal signature verification function (optional, see security note)
def verify_slack_signature(request):
    from hashlib import sha256
    import hmac
    timestamp = request.headers.get('X-Slack-Request-Timestamp')
    signature = request.headers.get('X-Slack-Signature')
    if not timestamp or not signature:
        return False
    req_body = request.get_data(as_text=True)
    sig_basestring = f"v0:{timestamp}:{req_body}"
    my_sig = 'v0=' + hmac.new(
        slack_signing_secret.encode(),
        sig_basestring.encode(),
        sha256
    ).hexdigest()
    return hmac.compare_digest(my_sig, signature)

app = Flask(__name__)

@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.get_json()
    # Respond to Slack's URL verification challenge
    if 'challenge' in data:
        return jsonify({'challenge': data['challenge']})

    # Optionally verify signature (recommended in production)
    # if not verify_slack_signature(request):
    #     return jsonify({'error': 'Invalid signature'}), 403

    # Process actual events (example: just print for now)
    print(f"Received event payload: {data}")
    return jsonify({'ok': True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)