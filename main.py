import os
import hmac
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from src.infrastructure.container import container
from src.infrastructure.config import settings

app = Flask(__name__)
# WSGI alias
application = app

# ---------------------------
# Middleware / Utils
# ---------------------------
def verify_slack_request(req) -> bool:
    if not settings.slack_signing_secret:
        return True
    timestamp = req.headers.get('X-Slack-Request-Timestamp', '')
    signature = req.headers.get('X-Slack-Signature', '')
    if not timestamp or not signature:
        return False
    
    req_body = req.get_data().decode('utf-8')
    sig_basestring = f'v0:{timestamp}:{req_body}'
    expected_signature = 'v0=' + hmac.new(
        settings.slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

@app.before_request
async def startup():
    # Naive 'startup' hook on first request or every request (idempotent init)
    # Ideally use a proper lifespan event if migrating to Quart/FastAPI
    if not getattr(app, '_db_init_done', False):
        await container.init_resources()
        app._db_init_done = True

# ---------------------------
# Routes
# ---------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'config': {
            'groq': bool(settings.groq_api_key),
            'slack': bool(settings.slack_bot_token),
            'jira': bool(settings.jira_base_url)
        }
    })

@app.route('/slack/events', methods=['POST'])
async def slack_events():
    if not verify_slack_request(request):
        return jsonify({'error': 'Invalid signature'}), 403

    data = request.get_json() or {}
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    if "event" in data:
        event = data["event"]
        if event.get("type") == "message" and not event.get("bot_id"):
            text = event.get("text", "")
            user = event.get("user", "")
            channel = event.get("channel", "")
            ts = event.get("ts", "")
            
            # Use Workflow from Container
            await container.workflow.process_message(text, channel, user, ts)
            return jsonify({'status': 'processed'})

    return jsonify({'status': 'ignored'})

@app.route('/reports/daily', methods=['GET'])
async def daily_report():
    date_str = request.args.get('date')
    if date_str:
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid date"}), 400
    else:
        date = datetime.now()

    report = await container.reporter.generate_daily_report(date, request.args.get('channel_id'))
    return jsonify({'report': report})

@app.route('/reports/weekly', methods=['GET'])
async def weekly_report():
    date_str = request.args.get('start_date')
    if date_str:
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid date"}), 400
    else:
        date = datetime.now()

    report = await container.reporter.generate_weekly_report(date, request.args.get('channel_id'))
    return jsonify({'report': report})

@app.route('/sop/generate', methods=['POST'])
async def generate_sop():
    data = request.get_json() or {}
    topic = data.get('topic')
    context = data.get('context', [])
    
    if not topic:
        return jsonify({'error': 'Topic required'}), 400
        
    readiness = await container.sop_gen.check_readiness(topic, context)
    if not readiness.is_complete:
        return jsonify({'status': 'incomplete', 'missing': readiness.missing_info})
        
    sop_text = await container.sop_gen.generate_sop(topic, context)
    
    # Save SOP
    from src.core.models.sop import Sop
    import time
    new_sop = Sop(
        title=f"SOP: {topic}",
        topic=topic,
        content=sop_text,
        created_at=int(time.time())
    )
    sop_id = await container.db.save_sop(new_sop)
    
    return jsonify({'status': 'created', 'id': sop_id, 'content': sop_text})


# ---------------------------
# Dashboard (Static)
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard_static")

@app.route('/dashboard')
def dashboard_index():
    return send_from_directory(DASHBOARD_DIR, "index.html")

@app.route('/dashboard/static/<path:filename>')
def dashboard_static(filename):
    return send_from_directory(DASHBOARD_DIR, filename)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)