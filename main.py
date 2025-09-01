import os
import re
import json
import time
import hashlib
import hmac
import requests
from flask import Flask, request, jsonify
from groq import Groq
from reporting import ReportsService, ReportsConfig, create_reports_blueprint
from report_commands import SlackReportCommandHandler, SlackReportCommandsConfig, create_slash_commands_blueprint
from sop_generator import SopConfig, SopService, SlackSopCommandHandler, create_sop_blueprint
from sop_readiness import SopReadinessService, SopReadinessConfig, create_sop_readiness_blueprint


app = Flask(__name__)

# ---------------------------
# Initialization and Config
# ---------------------------

# Initialize Groq client
try:
    groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
    print("✅ Groq client initialized successfully")
except Exception as e:
    print(f"❌ Groq initialization error: {e}")
    groq_client = None

# Model name
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

# Slack configuration
SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
TARGET_CHANNEL_ID = os.getenv('TARGET_CHANNEL_ID')
INSIGHTS_DB_PATH = os.getenv('INSIGHTS_DB_PATH', 'insights.db')
REPORT_POST_CHANNEL_ID = os.getenv('REPORT_POST_CHANNEL_ID', TARGET_CHANNEL_ID or '')
REPORT_INCLUDE_FACTS = os.getenv('REPORT_INCLUDE_FACTS', 'true').lower() == 'true'
REPORT_MAX_ITEMS = int(os.getenv('REPORT_MAX_ITEMS', '50'))
SOP_DEFAULT_DAYS = int(os.getenv('SOP_DEFAULT_DAYS', '14'))
SOP_MAX_CONTEXT_ITEMS = int(os.getenv('SOP_MAX_CONTEXT_ITEMS', '60'))
SOP_MODEL = os.getenv('SOP_MODEL', GROQ_MODEL)  # reuse existing model by default
SOP_READINESS_DEFAULT_DAYS = int(os.getenv('SOP_READINESS_DEFAULT_DAYS', '14'))
SOP_READINESS_MAX_CONTEXT_ITEMS = int(os.getenv('SOP_READINESS_MAX_CONTEXT_ITEMS', '60'))
SOP_READINESS_MODEL = os.getenv('SOP_READINESS_MODEL', GROQ_MODEL)
SOP_AUTOCHECK_BEFORE_GENERATE = os.getenv('SOP_AUTOCHECK_BEFORE_GENERATE', 'true').lower() == 'true'


# Noise filter configuration (tunable via env)
NOISE_FILTER_ENABLED = os.getenv('NOISE_FILTER_ENABLED', 'true').lower() == 'true'
NOISE_MIN_CHARS = int(os.getenv('NOISE_MIN_CHARS', '12'))            # quick heuristic
NOISE_LLM_THRESHOLD = float(os.getenv('NOISE_LLM_THRESHOLD', '0.55'))  # min confidence to accept LLM result
NOISE_DEBUG = os.getenv('NOISE_DEBUG', 'false').lower() == 'true'
# Treat short "help" or "question" messages as signal (default true)
NOISE_TREAT_HELP_AS_SIGNAL = os.getenv('NOISE_TREAT_HELP_AS_SIGNAL', 'true').lower() == 'true'
# If the classifier fails, default policy: allow (meaningful) or block
NOISE_FAILSAFE_POLICY = os.getenv('NOISE_FAILSAFE_POLICY', 'allow')  # 'allow' | 'block'


# ---------------------------
# Security: Slack Verification
# ---------------------------

def verify_slack_request(req) -> bool:
    """
    Verify the request is from Slack using signing secret.
    Falls back gracefully if no secret is set (dev mode).
    """
    if not SLACK_SIGNING_SECRET:
        return True

    # Prefer official headers; fall back to older non-hyphenated variants if present
    timestamp = req.headers.get('X-Slack-Request-Timestamp') or req.headers.get('XSlackRequestTimestamp', '')
    signature = req.headers.get('X-Slack-Signature') or req.headers.get('XSlackSignature', '')

    if not timestamp or not signature:
        return False

    # Optional replay protection
    try:
        if abs(time.time() - float(timestamp)) > 60 * 5:
            print("⚠️ Slack request timestamp out of acceptable range.")
    except Exception:
        pass

    req_body = req.get_data().decode('utf-8')
    sig_basestring = f'v0:{timestamp}:{req_body}'
    expected_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)



# ---------------------------
# Noise Filter: Heuristics
# ---------------------------

NOISE_ACKS = {
    "ok", "okay", "k", "kk", "yup", "yep", "yeah", "cool", "nice", "great",
    "awesome", "thanks", "thank you", "thx", "ty", "np", "no problem",
    "lol", "lmao", "haha", "hehe", "rofl", "gm", "gn", "brb", "gtg", "idk", "imo",
    "sounds good", "sgtm", "on it", "done", "agree", "ack", "nice one"
}

STRONG_SIGNAL_KEYWORDS = {
    "deadline", "eta", "due", "by eod", "tomorrow", "next week", "owner", "assign",
    "assigning", "assignment", "action", "todo", "to-do", "task", "follow up",
    "follow-up", "blocker", "blocked", "risk", "mitigate", "decision", "decide",
    "approved", "approve", "approval", "launch", "ship", "deploy", "rollback",
    "plan", "roadmap", "scope", "kpi", "okr", "metric", "sop", "process", "policy",
    "budget", "cost", "pricing", "contract", "legal", "sla", "incident", "postmortem",
    "meeting notes", "notes", "minutes", "summary", "next steps", "owner:", "assign to",
    "request", "please review", "review", "sign off", "sign-off", "requirement", "prd",
    "spec", "doc", "link:", "http://", "https://"
}

# Ask/help/question patterns we consider meaningful
ASK_SIGNAL_PATTERNS = [
    r"\b(help|assist|support)\b",
    r"\b(question|clarify|clarification)\b",
    r"\b(stuck|blocker|blocked|issue|bug|error|problem)\b",
    r"^\s*i need\b",
    r"^\s*we need\b",
]

EMOJI_RE = re.compile(r'^[\s\W_]+$')  # only punctuation/emoji/whitespace

def quick_noise_heuristic(text: str) -> str:
    """
    Fast local check.
    Returns:
      - 'noise' if clearly trivial
      - 'signal' if clearly meaningful
      - 'maybe' otherwise (defer to LLM)
    """
    t = (text or "").strip()
    tl = t.lower()

    # Minimum content length gate
    if len(tl) < NOISE_MIN_CHARS:
        return 'noise'

    # Only emojis/punctuation/whitespace
    if EMOJI_RE.match(tl):
        return 'noise'

    # Common acknowledgements / small talk (single-line)
    collapsed = re.sub(r'\s+', ' ', tl).strip()
    if collapsed in NOISE_ACKS:
        return 'noise'

    # Treat questions/help as signal (configurable)
    if NOISE_TREAT_HELP_AS_SIGNAL:
        if "?" in t and len(t) >= NOISE_MIN_CHARS:
            return 'signal'
        for pat in ASK_SIGNAL_PATTERNS:
            if re.search(pat, tl):
                return 'signal'

    # Strong signal keywords (clearly meaningful)
    for kw in STRONG_SIGNAL_KEYWORDS:
        if kw in tl:
            return 'signal'

    return 'maybe'


# ---------------------------
# JSON extraction helper for LLM responses
# ---------------------------

def extract_json_object(raw: str):
    """
    Robustly extract the first JSON object from a text that may include prose,
    code fences, or be empty. Returns dict or raises.
    """
    if not raw:
        raise ValueError("Empty LLM response")

    # Strip code fences if present
    s = raw.strip()
    if s.startswith("```"):
        # Remove leading and trailing fences
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)

    # If the whole thing parses, use it
    try:
        return json.loads(s)
    except Exception:
        pass

    # Otherwise, find the first balanced JSON object
    start = s.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = s[start:i+1]
                return json.loads(candidate)

    raise ValueError("Unbalanced JSON object in LLM response")


# ---------------------------
# Noise Filter: LLM Classifier
# ---------------------------

def classify_meaningfulness_with_groq(text: str) -> dict:
    """
    Uses LLM to classify if the message is meaningful.
    Returns dict:
      {
        "is_meaningful": bool,
        "category": "decision|todo|fact|update|question|process|noise",
        "confidence": float (0..1),
        "reason": str
      }
    """
    if not groq_client:
        return {
            "is_meaningful": True,
            "category": "update",
            "confidence": 0.99,  # high to avoid dropping signal when LLM unavailable
            "reason": "LLM unavailable; defaulting to meaningful to avoid losing signal."
        }

    prompt = f"""
You are a precise Slack message triage classifier.
Decide if the following message contains substantial, work-relevant content worth summarizing.

Signal (meaningful) examples:
- Decisions, proposals, approvals
- Action items, assignments, owners, deadlines, dates, next steps
- Status updates with specifics, blockers, risks, asks that require action
- Requirements, SOP/process info, metrics, links to specs/PRDs with context
- Meeting notes, summaries, handoffs, requests for help with context

Noise (not meaningful) examples:
- Greetings, thanks, jokes, emojis, small talk
- Single-word or short acknowledgements (e.g., "ok", "on it", "thanks")
- Vague replies with no new info (e.g., "sounds good")
- Standalone attachments or links without context
- Duplicates or trivial chatter

Return ONLY a JSON object in this exact schema:
{{
  "is_meaningful": true|false,
  "category": "decision|todo|fact|update|question|process|noise",
  "confidence": 0.0 to 1.0,
  "reason": "short explanation"
}}

Message:
\"\"\"{text}\"\"\"
"""

    try:
        resp = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            temperature=0.0,
            max_tokens=200,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if NOISE_DEBUG:
            print("🔎 LLM noise-classifier raw:", raw)

        result = extract_json_object(raw)

        # Validate fields
        is_meaningful = bool(result.get("is_meaningful"))
        category = str(result.get("category") or "noise")
        confidence = float(result.get("confidence") or 0.0)
        reason = str(result.get("reason") or "")
        return {
            "is_meaningful": is_meaningful,
            "category": category,
            "confidence": max(0.0, min(confidence, 1.0)),
            "reason": reason[:300],
        }
    except Exception as e:
        # Fail-safe based on policy
        print(f"⚠️ LLM classification error: {e}")
        if NOISE_FAILSAFE_POLICY == 'allow':
            return {
                "is_meaningful": True,
                "category": "update",
                "confidence": 0.99,   # ensure it passes threshold
                "reason": "Classifier failed; fail-safe allow to avoid dropping possible signal."
            }
        else:
            return {
                "is_meaningful": False,
                "category": "noise",
                "confidence": 0.99,
                "reason": "Classifier failed; fail-safe block."
            }


def is_message_meaningful(text: str) -> tuple[bool, dict]:
    """
    Combined gate:
      1) Fast heuristics
      2) LLM classifier if needed
    Returns: (bool meaningful, dict details)
    """
    if not NOISE_FILTER_ENABLED:
        return True, {"source": "disabled", "reason": "Noise filter disabled"}

    heuristic = quick_noise_heuristic(text)
    if heuristic == 'noise':
        decision = False
        info = {"source": "heuristic", "reason": "Short/ack/emoji/no-content"}
        if NOISE_DEBUG:
            print("🧭 Noise decision:", {"heuristic": heuristic, "final_meaningful": decision, "info": info})
        return decision, info
    if heuristic == 'signal':
        decision = True
        info = {"source": "heuristic", "reason": "Contains question/help or strong signal keywords"}
        if NOISE_DEBUG:
            print("🧭 Noise decision:", {"heuristic": heuristic, "final_meaningful": decision, "info": info})
        return decision, info

    # Ambiguous → LLM
    result = classify_meaningfulness_with_groq(text)
    meaningful = bool(result.get("is_meaningful", False)) and float(result.get("confidence", 0.0)) >= NOISE_LLM_THRESHOLD
    final_info = {"source": "llm", **result, "threshold": NOISE_LLM_THRESHOLD}
    if NOISE_DEBUG:
        print("🧭 Noise decision:", {"heuristic": heuristic, "llm": result, "final_meaningful": meaningful})
    return meaningful, final_info


# ---------------------------
# Insight Extraction (Existing)
# ---------------------------

def extract_insights_with_groq(text: str) -> dict:
    """
    Extract decisions, todos, and facts using Groq. Keeps existing prompt/format.
    """
    if not groq_client:
        print("⚠️ Groq client not available")
        return {"decisions": [], "todos": [], "facts": []}

    try:
        prompt = f"""
Extract insights from this message and respond with ONLY a JSON object:

Message: "{text}"

Required JSON format (no other text):
{{"decisions": ["any decisions made"], "todos": ["action items to do"], "facts": ["key facts or metrics"]}}
"""
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            temperature=0.1,
            max_tokens=500
        )
        result = response.choices[0].message.content.strip()
        print("🔎 Groq raw result:", result)

        try:
            parsed_result = json.loads(result)
            print("✅ Parsed insights:", parsed_result)
            return {
                "decisions": parsed_result.get("decisions", []) or [],
                "todos": parsed_result.get("todos", []) or [],
                "facts": parsed_result.get("facts", []) or [],
            }
        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to parse JSON: {e}")
            return {"decisions": [], "todos": [], "facts": []}
    except Exception as e:
        print(f"❌ Groq extraction error: {e}")
        return {"decisions": [], "todos": [], "facts": []}


# ---------------------------
# Slack Posting (Existing)
# ---------------------------

def post_to_slack_channel(channel_id: str, message: str) -> bool:
    """
    Post a message to a Slack channel using chat.postMessage.
    """
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "channel": channel_id,
        "text": message,
        "username": "AI Insights Bot",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        ok = resp.status_code == 200 and resp.json().get("ok", False)
        if not ok:
            print(f"⚠️ Slack API error: status={resp.status_code}, body={resp.text}")
        return ok
    except Exception as e:
        print(f"Slack post error: {e}")
        return False


def format_insights_for_slack(insights: dict, source_channel_id: str) -> str:
    """
    Format the extracted insights for Slack posting (existing style).
    """
    parts = ["🤖 *AI Insights Extracted:*", ""]
    if insights.get("decisions"):
        parts.append("⚡DECISIONS:")
        parts.extend([str(it) for it in insights["decisions"]])
        parts.append("")
    if insights.get("todos"):
        parts.append("📋TODOS:")
        parts.extend([str(it) for it in insights["todos"]])
        parts.append("")
    if insights.get("facts"):
        parts.append("💡FACTS:")
        parts.extend([str(it) for it in insights["facts"]])
        parts.append("")

    parts.append(f"_Source: <#{source_channel_id}>_")
    return "\n".join(parts)

# ---- Time-based Reports: service + blueprint registration ----
reports_service = ReportsService(
    ReportsConfig(
        db_path=INSIGHTS_DB_PATH,
        include_facts=REPORT_INCLUDE_FACTS,
        max_items=REPORT_MAX_ITEMS,
        default_post_channel_id=REPORT_POST_CHANNEL_ID or TARGET_CHANNEL_ID,
    )
)

reports_bp = create_reports_blueprint(
    service=reports_service,
    default_post_channel_id=REPORT_POST_CHANNEL_ID or TARGET_CHANNEL_ID,
    post_to_slack=post_to_slack_channel,  # reuse your existing Slack posting function
)
app.register_blueprint(reports_bp, url_prefix='/reports')
# ------------------------------------------------------------

# ---- SOP Readiness ----
sop_readiness_service = SopReadinessService(
    reports=reports_service,
    groq_client=groq_client,
    config=SopReadinessConfig(
        default_days=int(os.getenv('SOP_READINESS_DEFAULT_DAYS', '14')),
        max_context_items=int(os.getenv('SOP_READINESS_MAX_CONTEXT_ITEMS', '60')),
        default_post_channel_id=REPORT_POST_CHANNEL_ID or TARGET_CHANNEL_ID,
        model_name=os.getenv('SOP_READINESS_MODEL', GROQ_MODEL),
    ),
)
sop_readiness_bp = create_sop_readiness_blueprint(
    service=sop_readiness_service,
    post_to_slack=post_to_slack_channel,
)
app.register_blueprint(sop_readiness_bp, url_prefix="/sop")

# ---- SOP Generator ----
sop_service = SopService(
    reports_service=reports_service,
    groq_client=groq_client,
    post_to_slack=post_to_slack_channel,
    config=SopConfig(
        default_days=int(os.getenv('SOP_DEFAULT_DAYS', '14')),
        max_context_items=int(os.getenv('SOP_MAX_CONTEXT_ITEMS', '60')),
        default_post_channel_id=REPORT_POST_CHANNEL_ID or TARGET_CHANNEL_ID,
        model_name=os.getenv('SOP_MODEL', GROQ_MODEL),
    ),
)
sop_handler = SlackSopCommandHandler(sop_service=sop_service)


# ---- Enforce readiness before SOP generation (wrap the handler) ----
_original_handle_text_command = sop_handler.handle_text_command

def handle_sop_with_readiness(text: str, source_channel_id: str, user_id: str = None):
    import re as _re
    raw = _re.sub(r"^<@[^>]+>\s*", "", text or "")

    # Parse flags
    days = None
    m = _re.search(r"--days\s+(\d{1,3})", raw, flags=_re.IGNORECASE)
    if m:
        try:
            days = int(m.group(1))
            raw = raw[:m.start()] + raw[m.end():]
        except Exception:
            pass
    if _re.search(r"\bto\s+here\b", raw, flags=_re.IGNORECASE):
        raw = _re.sub(r"\bto\s+here\b", "", raw, flags=_re.IGNORECASE)

    # Extract topic (same patterns as the SOP handler)
    topic = None
    for pat in [
        r"^\s*sop\s+(?P<topic>.+)$",
        r"^\s*create\s+sop\s+for\s+(?P<topic>.+)$",
        r"^\s*create\s+sop\s+(?P<topic>.+)$",
        r"^\s*make\s+sop\s+for\s+(?P<topic>.+)$",
        r"^\s*make\s+sop\s+(?P<topic>.+)$",
    ]:
        mm = _re.match(pat, raw.strip(), flags=_re.IGNORECASE)
        if mm and mm.group("topic"):
            topic = mm.group("topic").strip()
            break

    # Readiness gate
    if SOP_AUTOCHECK_BEFORE_GENERATE and topic:
        readiness = sop_readiness_service.assess_readiness(topic=topic, channel_id=source_channel_id, days=days)
        if not readiness.get("is_complete", False):
            prompt = readiness.get("clarification_prompt") or \
                     f"To complete the SOP for '{topic}', please provide goals, scope, roles, tools/systems, and numbered steps with acceptance criteria."
            post_to_slack_channel(source_channel_id, f"🧭 *SOP Readiness Check: {topic}*\n\n{prompt}")
            return {
                "ok": True,
                "posted": True,
                "message": "Clarification requested before SOP generation.",
                "topic": topic,
                "is_complete": False,
                "context_counts": readiness.get("context_counts", {}),
                "window": {"start": readiness.get("window_start"), "end": readiness.get("window_end")},
            }

    # Otherwise, proceed with original SOP generation path
    return _original_handle_text_command(text=text, source_channel_id=source_channel_id, user_id=user_id)

# Monkey-patch so all callers (slash + mentions) go through readiness first
sop_handler.handle_text_command = handle_sop_with_readiness
# -------------------------------------------------------------------


sop_bp = create_sop_blueprint(sop_handler, verify_slack_request)
app.register_blueprint(sop_bp, url_prefix="/sop")


# ---- Report Commands: handler + slash command blueprint ----
report_commands_handler = SlackReportCommandHandler(
    service=reports_service,
    post_to_slack=post_to_slack_channel,
    config=SlackReportCommandsConfig(
        default_post_channel_id=REPORT_POST_CHANNEL_ID or TARGET_CHANNEL_ID
    ),
)

commands_bp = create_slash_commands_blueprint(
    handler=report_commands_handler,
    signature_verifier=verify_slack_request,  # reuse your Slack signing verification
)
app.register_blueprint(commands_bp, url_prefix="/slack")
# ------------------------------------------------------------


# ---- SOP Readiness: service + blueprint ----
sop_readiness_service = SopReadinessService(
    reports=reports_service,
    groq_client=groq_client,
    config=SopReadinessConfig(
        default_days=SOP_READINESS_DEFAULT_DAYS,
        max_context_items=SOP_READINESS_MAX_CONTEXT_ITEMS,
        default_post_channel_id=REPORT_POST_CHANNEL_ID or TARGET_CHANNEL_ID,
        model_name=SOP_READINESS_MODEL,
    ),
)
sop_readiness_bp = create_sop_readiness_blueprint(
    service=sop_readiness_service,
    post_to_slack=post_to_slack_channel,
)
app.register_blueprint(sop_readiness_bp, url_prefix="/sop")
# -------------------------------------------------------


# ---- SOP: service + handler + blueprint ----
sop_service = SopService(
    reports_service=reports_service,
    groq_client=groq_client,
    post_to_slack=post_to_slack_channel,
    config=SopConfig(
        default_days=SOP_DEFAULT_DAYS,
        max_context_items=SOP_MAX_CONTEXT_ITEMS,
        default_post_channel_id=REPORT_POST_CHANNEL_ID or TARGET_CHANNEL_ID,
        model_name=SOP_MODEL,
    ),
)

sop_handler = SlackSopCommandHandler(sop_service=sop_service)
sop_bp = create_sop_blueprint(sop_handler, verify_slack_request)
app.register_blueprint(sop_bp, url_prefix="/sop")
# --------------------------------------------



# ---------------------------
# Health + Root Endpoints
# ---------------------------

@app.route('/', methods=['GET'])
def root():
    return jsonify({"status": "ok", "service": "AI Shadow Coach", "message": "Running"}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'groq_configured': bool(os.getenv('GROQ_API_KEY')),
        'slack_configured': bool(SLACK_BOT_TOKEN),
        'target_channel': bool(TARGET_CHANNEL_ID),
        'noise_filter_enabled': NOISE_FILTER_ENABLED,
        'noise_min_chars': NOISE_MIN_CHARS,
        'noise_llm_threshold': NOISE_LLM_THRESHOLD,
        'noise_treat_help_as_signal': NOISE_TREAT_HELP_AS_SIGNAL,
        'noise_failsafe_policy': NOISE_FAILSAFE_POLICY
    })


# ---------------------------
# Slack Events (Gated by noise filter)
# ---------------------------

@app.route('/slack/events', methods=['POST'])
def slack_events():
    # Verify request is from Slack
    if not verify_slack_request(request):
        return jsonify({'error': 'Invalid signature'}), 403

    data = request.get_json() or {}

    # Handle Slack URL verification
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    # Process events
    if "event" in data:
        event = data["event"]

        # Handle message events
        if event.get("type") == "message":
            # Skip bot messages and message changes
            if "bot_id" in event or "subtype" in event:
                return jsonify({'status': 'ignored_bot_message'})

            message_text = event.get("text", "") or ""
            user_id = event.get("user", "") or ""
            channel_id = event.get("channel", "") or ""

            # Skip empty messages
            if not message_text.strip():
                return jsonify({'status': 'empty_message'})

            print(f"📨 Processing message from user {user_id}: {message_text[:100]}...")
            if event.get("type") == "message":
                # Skip bot messages and message changes
                if "bot_id" in event or "subtype" in event:
                    return jsonify({'status': 'ignored_bot_message'})

                message_text = event.get("text", "") or ""
                user_id = event.get("user", "") or ""
                channel_id = event.get("channel", "") or ""

                # 0) SOP trigger: "@Bot sop <topic>", "sop <topic>", "create sop for <topic>"
                mention_or_text = (message_text or "").strip().lower()
                if event.get("channel_type") in {"channel", "group", "im", "mpim"}:
                    try:
                        # Try parsing as an SOP command. If it fails, we ignore and continue.
                        if (
                                mention_or_text.startswith("sop ")
                                or mention_or_text.startswith("create sop")
                                or mention_or_text.startswith("<@")
                        ) and (" sop " in mention_or_text or mention_or_text.startswith("sop ")):
                            sop_result = sop_handler.handle_text_command(
                                text=message_text,  # raw text, handler strips mentions
                                source_channel_id=channel_id,
                                user_id=user_id,
                            )
                            return jsonify({
                                "status": "sop_generated",
                                "posted": sop_result["posted"],
                                "topic": sop_result["topic"],
                                "days": sop_result["days"],
                                "context_counts": sop_result["context_counts"],
                                "target_channel": sop_result["target_channel_id"],
                            })
                    except ValueError:
                        # Not a valid SOP command; continue with normal flow
                        pass
                    except Exception as e:
                        # Surface as handled error but don't break other flows
                        return jsonify({"status": "sop_error", "error": str(e)}), 200

                # 1) App mention: "<@Uxxxx> report daily [YYYY-MM-DD]"
                if event.get("channel_type") in {"channel", "group", "im", "mpim"}:
                    mention_or_report = message_text.strip().lower()
                    if mention_or_report.startswith("report ") or mention_or_report.startswith("<@"):
                        # Try to interpret as a report command. If it fails, fall through to normal flow.
                        try:
                            result = report_commands_handler.handle_text_command(
                                source_channel_id=channel_id,
                                text=message_text,
                                user_id=user_id,
                            )
                            return jsonify({
                                'status': 'report_posted',
                                'posted': result["posted"],
                                'period': result["period"],
                                'date_or_week_start': result["date_or_week_start"],
                                'counts': result["counts"],
                                'target_channel': result["target_channel_id"],
                            })
                        except ValueError:
                            # Not a valid report command; continue with the normal pipeline
                            pass

            # Noise filter gate
            is_meaningful, filter_info = is_message_meaningful(message_text)
            print(f"🧩 Noise filter result: meaningful={is_meaningful}, info={filter_info}")

            if not is_meaningful:
                return jsonify({'status': 'noise_filtered', 'reason': filter_info})

            # Extract insights
            insights = extract_insights_with_groq(message_text)

            # If any insights, format and post
            if any(insights.get(key) for key in ["decisions", "todos", "facts"]):
                reports_service.save_insights(
                    channel_id=channel_id,
                    user_id=user_id,
                    message_text=message_text,
                    insights=insights,
                )
                formatted_message = format_insights_for_slack(insights, channel_id)

                # Post to target channel
                if TARGET_CHANNEL_ID:
                    success = post_to_slack_channel(TARGET_CHANNEL_ID, formatted_message)
                    if success:
                        print("✅ Posted insights to target channel")
                    else:
                        print("❌ Failed to post to target channel")
                else:
                    print("⚠️ TARGET_CHANNEL_ID not configured; skipping post")

                return jsonify({'status': 'processed', 'insights_found': True})

            # No insights extracted
            print("ℹ️ No significant insights found in message")
            return jsonify({'status': 'no_insights'})

    return jsonify({'status': 'event_ignored'})


# ---------------------------
# Test Endpoint (Existing)
# ---------------------------

@app.route('/test-slack', methods=['GET'])
def test_slack():
    test_message = "🧪 Test message from bot!"
    if TARGET_CHANNEL_ID:
        success = post_to_slack_channel(TARGET_CHANNEL_ID, test_message)
        return jsonify({
            'success': success,
            'target_channel': TARGET_CHANNEL_ID,
            'bot_token_configured': bool(SLACK_BOT_TOKEN)
        })
    else:
        return jsonify({'error': 'No TARGET_CHANNEL_ID configured'})


# ---------------------------
# Entry Point
# ---------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)