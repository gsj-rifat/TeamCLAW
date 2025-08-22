import os
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200


@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.get_json() or {}

    # Handle Slack challenge
    if "challenge" in data:
        return jsonify({"challenge": data['challenge']})

    return jsonify({'status': 'success'})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
