import os
import re
import json
import time
import hashlib
import hmac
import requests
from groq import Groq
from reporting import ReportsService, ReportsConfig, create_reports_blueprint
from report_commands import SlackReportCommandHandler, SlackReportCommandsConfig, create_slash_commands_blueprint
from sop_generator import SopConfig, SopService, SlackSopCommandHandler, create_sop_blueprint
from sop_readiness import SopReadinessService, SopReadinessConfig, create_sop_readiness_blueprint
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, Blueprint, send_from_directory, redirect, abort

app = Flask(__name__)
# WSGI alias for gunicorn (main:application)
application = app


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

BASE_DIR = os.path.dirname(__file__)  # /opt/render/project/src at runtime
INSIGHTS_DB_PATH = os.getenv("INSIGHTS_DB_PATH", os.path.join(BASE_DIR, "insights.db"))


DISABLE_DASHBOARD_AUTH = os.getenv("DISABLE_DASHBOARD_AUTH", "true").lower() in ("1", "true", "yes")
DEFAULT_PUBLIC_ROLE = os.getenv("DEFAULT_PUBLIC_ROLE", "admin")  # or "admin" if you want full access
ROLE_LEVEL = {"viewer": 1, "user": 2, "admin": 3}


# Role resolution no longer used; kept only to satisfy references
# Keep a harmless role function for compatibility with any code that calls it
def current_role():
    return "public"
# Make require_role a no-op (in case any endpoints still use it)
def require_role(arg=None):
    if callable(arg):
        # used as @require_role without parentheses
        return arg
    def decorator(fn):
        return fn
    return decorator
# CRITICAL: Make require_dashboard_role a no-op so all @require_dashboard_role(...) wrappers allow access
def require_dashboard_role(*allowed_roles):
    # Supports both @require_dashboard_role and @require_dashboard_role(...)
    if len(allowed_roles) == 1 and callable(allowed_roles[0]):
        # decorator used without parentheses
        return allowed_roles[0]
    def decorator(fn):
        return fn
    return decorator
# Ensure the auth probe is public and consistent
# If this route is already defined, replace its body with this version and REMOVE any require_dashboard_role on it
@app.get("/dashboard/api/auth/me")
def auth_me_public():
    return jsonify({"status": "ok", "role": "public"})


# ---------------------------
# Dashboard API Auth (X-Auth-Token)
# ---------------------------

DEV_MODE = os.getenv("RENDER", "false").lower() != "true"

def _load_dashboard_tokens():
    raw = os.getenv("DASHBOARD_TOKENS", "{}")
    try:
        return json.loads(raw)
    except Exception:
        return {}

_DASHBOARD_TOKENS = _load_dashboard_tokens()

def _get_role_from_request(req):
    # Header names tolerated
    token = (req.headers.get("X-Auth-Token") or req.headers.get("XAuthToken") or "").strip()
    role = _DASHBOARD_TOKENS.get(token)
    if role:
        return role
    # If no tokens are configured, allow read-only access in local dev for convenience
    if not _DASHBOARD_TOKENS and DEV_MODE:
        return "viewer"
    return None

# ---------------------------
# Dashboard Auth (viewer/user/admin) via env tokens
# ---------------------------

def _parse_token_list(raw: str) -> set[str]:
    if not raw:
        return set()
    # Accept comma or whitespace separated
    parts = []
    for chunk in raw.replace(",", " ").split():
        t = chunk.strip()
        if t:
            parts.append(t)
    return set(parts)

DASHBOARD_VIEWER_TOKENS = _parse_token_list(os.getenv("DASHBOARD_VIEWER_TOKENS", ""))
DASHBOARD_USER_TOKENS   = _parse_token_list(os.getenv("DASHBOARD_USER_TOKENS", ""))
DASHBOARD_ADMIN_TOKENS  = _parse_token_list(os.getenv("DASHBOARD_ADMIN_TOKENS", ""))

ROLE_RANK = {"viewer": 0, "user": 1, "admin": 2}

def _extract_token_from_request(req) -> str | None:
    # Prefer custom header used by the dashboard
    tok = (req.headers.get("X-Auth-Token") or "").strip()
    if tok:
        return tok
    # Fallback: Authorization: Bearer <token>
    auth = req.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    # Optional: dev fallback to query param ?token=
    q = req.args.get("token")
    if q and q.strip():
        return q.strip()
    return None

def resolve_dashboard_role_from_token(tok: str | None) -> str | None:
    if not tok:
        return None
    if tok in DASHBOARD_ADMIN_TOKENS:
        return "admin"
    if tok in DASHBOARD_USER_TOKENS:
        return "user"
    if tok in DASHBOARD_VIEWER_TOKENS:
        return "viewer"
    return None

def require_dashboard_role(*allowed_roles: str):
    """
    Decorator to protect dashboard API endpoints with role-based auth.
    Usage: @require_dashboard_role("viewer","user","admin")  # allow all
           @require_dashboard_role("user","admin")
           @require_dashboard_role("admin")
    """
    def _decorator(fn):
        from functools import wraps
        @wraps(fn)
        def _wrapped(*args, **kwargs):
            token = _extract_token_from_request(request)
            role = resolve_dashboard_role_from_token(token)
            if role is None:
                return jsonify({"error": "Unauthorized"}), 401
            if allowed_roles and role not in allowed_roles:
                return jsonify({"error": "Forbidden", "role": role}), 403
            # ok
            return fn(*args, **kwargs)
        return _wrapped
    return _decorator



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

print(f"[startup] Using DB at {INSIGHTS_DB_PATH}", flush=True)

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

    # NEW: parse --force and remove it from the text we pass onward
    force = bool(_re.search(r"(?:^|\s)--force(?:\s|$)", raw, flags=_re.IGNORECASE))
    sanitized_text = _re.sub(r"(?:^|\s)--force(?:\s|$)", " ", text or "", flags=_re.IGNORECASE)

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

    # Readiness gate (skip if --force present)
    if SOP_AUTOCHECK_BEFORE_GENERATE and topic and not force:
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

    # If --force, or readiness is complete, proceed to original handler.
    # IMPORTANT: pass sanitized_text (without --force) so the original parser accepts it.
    return _original_handle_text_command(text=sanitized_text, source_channel_id=source_channel_id, user_id=user_id)

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


# ---------------------------
# Dashboard API (read-only MVP)
# ---------------------------

dashboard_api = Blueprint("dashboard_api", __name__)

def _db_connect_for_dashboard():
    # Reuse the ReportsService connection (same SQLite DB)
    return reports_service._connect()

@dashboard_api.get("/stats")
@require_dashboard_role("viewer", "user", "admin")
def dashboard_stats():
    """
    Counts of insights for today and this week (UTC).
    SOPs and summaries will remain 0 in Step 2 (filled in later steps).
    """
    try:
        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        today_end = today_start + timedelta(days=1)

        week_start = today_start - timedelta(days=today_start.weekday())  # Monday UTC
        week_end = week_start + timedelta(days=7)

        conn = _db_connect_for_dashboard()
        cur = conn.cursor()

        def _count_insights(start_dt, end_dt):
            cur.execute(
                "SELECT COUNT(*) AS c FROM insights WHERE created_at >= ? AND created_at < ?",
                (int(start_dt.timestamp()), int(end_dt.timestamp())),
            )
            row = cur.fetchone()
            return int((row["c"] if row else 0) or 0)

        insights_today = _count_insights(today_start, today_end)
        insights_week = _count_insights(week_start, week_end)

        conn.close()
        return jsonify({
            "status": "ok",
            "stats": {
                "insights": {"today": insights_today, "week": insights_week},
                "sops": {"today": 0, "week": 0},
                "summaries": {"today": 0, "week": 0},
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@dashboard_api.get("/activities")
@require_dashboard_role("viewer", "user", "admin")
def dashboard_activities():
    """
    Recent insight events derived from the insights table.
    """
    try:
        limit = int(request.args.get("limit", "100"))
        conn = _db_connect_for_dashboard()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, created_at, channel_id, message_text, decisions, todos, facts
            FROM insights
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        conn.close()

        items = []
        for r in rows:
            try:
                dec = len(json.loads(r["decisions"] or "[]"))
            except Exception:
                dec = 0
            try:
                tds = len(json.loads(r["todos"] or "[]"))
            except Exception:
                tds = 0
            try:
                fcts = len(json.loads(r["facts"] or "[]"))
            except Exception:
                fcts = 0

            items.append({
                "id": r["id"],
                "timestamp": int(r["created_at"]),
                "type": "insight_saved",
                "channel_id": r["channel_id"] or "",
                "meta": {
                    "message_preview": (r["message_text"] or "")[:140],
                    "counts": {"decisions": dec, "todos": tds, "facts": fcts},
                }
            })

        return jsonify({"status": "ok", "items": items})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ---------------------------
# Reports (read-only)
# ---------------------------

@dashboard_api.get("/reports")
@require_dashboard_role("viewer", "user", "admin")
def dashboard_reports():
    """
    Generate daily or weekly reports for a date range (UTC), optionally filtered by channel_id.
    Query params:
      - granularity: "daily" (default) or "weekly"
      - start: YYYY-MM-DD (required)
      - end:   YYYY-MM-DD (required; inclusive range)
      - channel_id: optional Slack channel ID to filter
    Response:
      { status: "ok", items: [ { period, label, channel_filter, counts, report_text }, ... ] }
    """
    try:
        granularity = (request.args.get("granularity") or "daily").lower()
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        channel_id = request.args.get("channel_id")

        if granularity not in ("daily", "weekly"):
            return jsonify({"error": "granularity must be 'daily' or 'weekly'"}), 400
        if not start_str or not end_str:
            return jsonify({"error": "start and end (YYYY-MM-DD) are required"}), 400

        # Parse dates (UTC boundaries)
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt_inclusive = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        # Iterate periods and build reports
        items = []
        if granularity == "daily":
            cur = start_dt
            final = end_dt_inclusive + timedelta(days=1)  # exclusive bound
            while cur < final:
                period_start = cur
                period_end = cur + timedelta(days=1)
                rows = reports_service.fetch_between(int(period_start.timestamp()), int(period_end.timestamp()), channel_id)
                aggs = reports_service.build_aggregates(rows)
                text = reports_service.generate_report_text("Daily", period_start, period_end, channel_id, aggs)
                items.append({
                    "period": "daily",
                    "label": period_start.strftime("%Y-%m-%d"),
                    "channel_filter": channel_id,
                    "counts": {k: len(aggs.get(k, [])) for k in ("decisions", "todos", "facts")},
                    "report_text": text
                })
                cur = period_end
        else:
            # Weekly periods start on Monday (UTC)
            # Align the cursor to the Monday of the start week
            start_monday = start_dt - timedelta(days=start_dt.weekday())
            cur = datetime(start_monday.year, start_monday.month, start_monday.day, tzinfo=timezone.utc)
            final = end_dt_inclusive + timedelta(days=1)  # exclusive bound
            while cur < final:
                period_start = cur
                period_end = period_start + timedelta(days=7)
                rows = reports_service.fetch_between(int(period_start.timestamp()), int(period_end.timestamp()), channel_id)
                aggs = reports_service.build_aggregates(rows)
                text = reports_service.generate_report_text("Weekly", period_start, period_end, channel_id, aggs)
                items.append({
                    "period": "weekly",
                    "label": period_start.strftime("%Y-%m-%d"),  # Monday label
                    "channel_filter": channel_id,
                    "counts": {k: len(aggs.get(k, [])) for k in ("decisions", "todos", "facts")},
                    "report_text": text
                })
                cur = period_end

        return jsonify({"status": "ok", "items": items})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@dashboard_api.get("/reports/export.csv")
@require_dashboard_role("viewer", "user", "admin")
def dashboard_reports_export_csv():
    """
    Export a single period as CSV.
    Query params:
      - granularity: "daily" or "weekly"
      - date: YYYY-MM-DD  (for daily: the day; for weekly: Monday of the week)
      - channel_id: optional
    """
    try:
        import io, csv

        granularity = (request.args.get("granularity") or "daily").lower()
        date_str = request.args.get("date")
        channel_id = request.args.get("channel_id")

        if granularity not in ("daily", "weekly"):
            return jsonify({"error": "granularity must be 'daily' or 'weekly'"}), 400
        if not date_str:
            return jsonify({"error": "date (YYYY-MM-DD) is required"}), 400

        try:
            start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        if granularity == "daily":
            end = start + timedelta(days=1)
            label = "Daily"
            start_label = start.strftime("%Y-%m-%d")
            end_label = (end - timedelta(seconds=1)).strftime("%Y-%m-%d")
        else:
            # Treat given date as the week start (Monday)
            week_monday = start - timedelta(days=start.weekday())
            start = datetime(week_monday.year, week_monday.month, week_monday.day, tzinfo=timezone.utc)
            end = start + timedelta(days=7)
            label = "Weekly"
            start_label = start.strftime("%Y-%m-%d")
            end_label = (end - timedelta(seconds=1)).strftime("%Y-%m-%d")

        rows = reports_service.fetch_between(int(start.timestamp()), int(end.timestamp()), channel_id)
        aggs = reports_service.build_aggregates(rows)

        # Build CSV
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Period", "Start", "End", "Channel", "Type", "Item"])
        for t in ("decisions", "todos", "facts"):
            for item in aggs.get(t, []):
                writer.writerow([label, start_label, end_label, channel_id or "", t, item])

        csv_bytes = buf.getvalue()
        resp = app.response_class(csv_bytes, mimetype="text/csv")
        safe_date = start_label
        resp.headers["Content-Disposition"] = f'attachment; filename=report_{label.lower()}_{safe_date}.csv'
        return resp
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ---------------------------
# SOP Library (list/create/edit/delete)
# ---------------------------

def _ensure_sops_table(conn):
    cur = conn.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS sops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER,
        topic TEXT NOT NULL,
        channel_id TEXT,
        tags TEXT,
        author_user_id TEXT,
        version TEXT,
        status TEXT,
        sop_text TEXT NOT NULL
      )
    """)
    conn.commit()

@dashboard_api.get("/sops")
@require_dashboard_role("viewer", "user", "admin")
def sops_list():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    try:
        conn = reports_service._connect()
        _ensure_sops_table(conn)
        cur = conn.cursor()
        if q and status:
            cur.execute("""
                SELECT * FROM sops
                WHERE (topic LIKE ? OR tags LIKE ? OR sop_text LIKE ?)
                AND status = ?
                ORDER BY created_at DESC
                LIMIT 200
            """, (f"%{q}%", f"%{q}%", f"%{q}%", status))
        elif q:
            cur.execute("""
                SELECT * FROM sops
                WHERE topic LIKE ? OR tags LIKE ? OR sop_text LIKE ?
                ORDER BY created_at DESC
                LIMIT 200
            """, (f"%{q}%", f"%{q}%", f"%{q}%"))
        elif status:
            cur.execute("""
                SELECT * FROM sops
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT 200
            """, (status,))
        else:
            cur.execute("""SELECT * FROM sops ORDER BY created_at DESC LIMIT 200""")
        rows = cur.fetchall()
        conn.close()
        items = [{
            "id": r["id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "topic": r["topic"],
            "channel_id": r["channel_id"],
            "tags": r["tags"],
            "author_user_id": r["author_user_id"],
            "version": r["version"],
            "status": r["status"],
            "sop_text": r["sop_text"],
        } for r in rows]
        return jsonify({"status":"ok","items":items})
    except Exception as e:
        return jsonify({"status":"error","error":str(e)}), 500

@dashboard_api.post("/sops")
@require_dashboard_role("user", "admin")
def sops_create():
    payload = request.get_json() or {}
    topic = (payload.get("topic") or "").strip()
    if not topic:
        return jsonify({"error":"topic is required"}), 400
    channel_id = (payload.get("channel_id") or "").strip() or None
    tags = (payload.get("tags") or "").strip()
    author_user_id = (payload.get("author_user_id") or "").strip()
    version = (payload.get("version") or "v1").strip()
    status = (payload.get("status") or "active").strip()
    generate = bool(payload.get("generate", False))
    days = payload.get("days")

    try:
        if generate:
            # Use existing SOP generator logic (no posting)
            res = sop_service.generate_sop_text(topic=topic, channel_id=channel_id, days=days)
            sop_text = res["sop_text"]
        else:
            sop_text = (payload.get("sop_text") or "").strip()
            if not sop_text:
                return jsonify({"error":"sop_text required when generate=false"}), 400

        now_ts = int(time.time())
        conn = reports_service._connect()
        _ensure_sops_table(conn)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sops (created_at, updated_at, topic, channel_id, tags, author_user_id, version, status, sop_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now_ts, now_ts, topic, channel_id, tags, author_user_id, version, status, sop_text))
        sop_id = cur.lastrowid
        conn.commit(); conn.close()
        return jsonify({"status":"ok","id": sop_id})
    except Exception as e:
        return jsonify({"status":"error","error":str(e)}), 500

@dashboard_api.put("/sops/<int:sop_id>")
@require_dashboard_role("user", "admin")
def sops_update(sop_id: int):
    payload = request.get_json() or {}
    fields, values = [], []
    for key in ("topic","channel_id","tags","author_user_id","version","status","sop_text"):
        if key in payload:
            fields.append(f"{key}=?")
            values.append(payload[key])
    if not fields:
        return jsonify({"error":"no fields to update"}), 400

    try:
        conn = reports_service._connect()
        _ensure_sops_table(conn)
        cur = conn.cursor()
        values.append(int(time.time()))
        values.append(sop_id)
        cur.execute(f"UPDATE sops SET {', '.join(fields)}, updated_at=? WHERE id=?", values)
        conn.commit(); conn.close()
        return jsonify({"status":"ok"})
    except Exception as e:
        return jsonify({"status":"error","error":str(e)}), 500

@dashboard_api.delete("/sops/<int:sop_id>")
@require_dashboard_role("admin")
def sops_delete(sop_id: int):
    try:
        conn = reports_service._connect()
        _ensure_sops_table(conn)
        cur = conn.cursor()
        cur.execute("DELETE FROM sops WHERE id=?", (sop_id,))
        conn.commit(); conn.close()
        return jsonify({"status":"ok"})
    except Exception as e:
        return jsonify({"status":"error","error":str(e)}), 500

# ---------------------------
# Summaries Archive (search/filter/create)
# ---------------------------

def _ensure_summaries_table(conn):
    cur = conn.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER,
        -- window captured for the summary
        period_start INTEGER,
        period_end INTEGER,
        -- quick label fields
        date TEXT,
        channel_id TEXT,
        author_user_id TEXT,
        title TEXT NOT NULL,
        summary_text TEXT NOT NULL,
        tags TEXT,
        status TEXT
      )
    """)
    conn.commit()

def _generate_summary_text(title: str, start_dt: datetime, end_dt: datetime, channel_id: str | None) -> str:
    """
    Generates a concise summary using the existing insights:
      - If Groq is configured, ask for a prose summary
      - Otherwise, produce a deterministic bullet summary from aggregates
    """
    rows = reports_service.fetch_between(int(start_dt.timestamp()), int(end_dt.timestamp()), channel_id)
    aggs = reports_service.build_aggregates(rows)

    # Try LLM first if available
    if groq_client:
        decisions = "\n".join(f"- {x}" for x in (aggs.get("decisions") or [])[:15]) or "- (none)"
        todos = "\n".join(f"- {x}" for x in (aggs.get("todos") or [])[:15]) or "- (none)"
        facts = "\n".join(f"- {x}" for x in (aggs.get("facts") or [])[:15]) or "- (none)"
        prompt = f"""
You are an expert note-taker. Write a concise, executive-friendly summary (120–180 words)
for the window {start_dt.strftime('%Y-%m-%d')} → {(end_dt - timedelta(seconds=1)).strftime('%Y-%m-%d')} UTC
{f'for Slack channel <#{channel_id}>' if channel_id else ''} titled: "{title}".

Ground ONLY in these items. Prefer synthesis over copying.

Decisions:
{decisions}

To-Dos:
{todos}

Facts:
{facts}

Output plain text suitable for Slack (no headers, no JSON).
"""
        try:
            resp = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=GROQ_MODEL,
                temperature=0.2,
                max_tokens=400,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception as _e:
            pass  # fall back to deterministic summary

    # Deterministic fallback (no LLM)
    lines = []
    lines.append(f"{title} — Summary ({start_dt.strftime('%Y-%m-%d')} → {(end_dt - timedelta(seconds=1)).strftime('%Y-%m-%d')} UTC){f' — Channel: #{channel_id}' if channel_id else ''}")
    lines.append("")
    if aggs.get("decisions"):
        lines.append(f"Decisions ({len(aggs['decisions'])}):")
        lines.extend([f"- {x}" for x in aggs["decisions"][:10]])
        lines.append("")
    if aggs.get("todos"):
        lines.append(f"To-Dos ({len(aggs['todos'])}):")
        lines.extend([f"- {x}" for x in aggs["todos"][:10]])
        lines.append("")
    if aggs.get("facts"):
        lines.append(f"Facts ({len(aggs['facts'])}):")
        lines.extend([f"- {x}" for x in aggs["facts"][:10]])
        lines.append("")
    if not any(aggs.get(k) for k in ("decisions","todos","facts")):
        lines.append("_No insights collected for this window._")
    return "\n".join(lines)


@dashboard_api.get("/summaries")
@require_dashboard_role("viewer", "user", "admin")
def summaries_list():
    """
    Search/filter the summaries archive.
    Query params:
      - q: free-text search in title/tags/summary_text
      - status: filter by status (e.g., draft|active|archived)
      - channel_id: optional filter
      - start: YYYY-MM-DD (filter by period_start >= start)
      - end: YYYY-MM-DD (filter by period_start < end+1 day)
      - limit: max rows (default 100)
    """
    try:
        q = (request.args.get("q") or "").strip()
        status = (request.args.get("status") or "").strip()
        channel_id = (request.args.get("channel_id") or "").strip()
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        limit = max(1, min(500, int(request.args.get("limit") or "100")))

        start_ts = end_ts = None
        if start_str:
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                start_ts = int(start_dt.timestamp())
            except ValueError:
                return jsonify({"error": "Invalid 'start' format. Use YYYY-MM-DD"}), 400
        if end_str:
            try:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
                end_ts = int(end_dt.timestamp())  # exclusive
            except ValueError:
                return jsonify({"error": "Invalid 'end' format. Use YYYY-MM-DD"}), 400

        conn = reports_service._connect()
        _ensure_summaries_table(conn)
        cur = conn.cursor()

        sql = "SELECT * FROM summaries WHERE 1=1"
        params = []

        if q:
            sql += " AND (title LIKE ? OR tags LIKE ? OR summary_text LIKE ?)"
            like = f"%{q}%"
            params.extend([like, like, like])
        if status:
            sql += " AND status = ?"
            params.append(status)
        if channel_id:
            sql += " AND channel_id = ?"
            params.append(channel_id)
        if start_ts is not None:
            sql += " AND (period_start IS NULL OR period_start >= ?)"
            params.append(start_ts)
        if end_ts is not None:
            sql += " AND (period_start IS NULL OR period_start < ?)"
            params.append(end_ts)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        conn.close()

        items = [{
            "id": r["id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "period_start": r["period_start"],
            "period_end": r["period_end"],
            "date": r["date"],
            "channel_id": r["channel_id"],
            "author_user_id": r["author_user_id"],
            "title": r["title"],
            "tags": r["tags"],
            "status": r["status"],
            "summary_text": r["summary_text"],
        } for r in rows]

        return jsonify({"status":"ok","items":items})
    except Exception as e:
        return jsonify({"status":"error","error":str(e)}), 500


@dashboard_api.post("/summaries")
@require_dashboard_role("user", "admin")
def summaries_create():
    """
    Create a summary.
    JSON body:
      - title: required
      - channel_id: optional
      - tags: optional
      - status: optional (default: active)
      - author_user_id: optional
      EITHER:
        - generate: true, with start, end (YYYY-MM-DD), optional channel_id
      OR
        - generate: false (default), with summary_text (required)
    """
    try:
        payload = request.get_json() or {}
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify({"error":"title is required"}), 400

        channel_id = (payload.get("channel_id") or "").strip() or None
        tags = (payload.get("tags") or "").strip()
        status = (payload.get("status") or "active").strip()
        author_user_id = (payload.get("author_user_id") or "").strip()
        generate = bool(payload.get("generate", False))

        period_start_ts = period_end_ts = None
        date_label = None

        if generate:
            start_str = payload.get("start")
            end_str = payload.get("end")
            if not start_str or not end_str:
                return jsonify({"error":"start and end (YYYY-MM-DD) are required when generate=true"}), 400
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

            date_label = start_dt.strftime("%Y-%m-%d")
            period_start_ts = int(start_dt.timestamp())
            period_end_ts = int(end_dt.timestamp())
            summary_text = _generate_summary_text(title, start_dt, end_dt, channel_id)
        else:
            summary_text = (payload.get("summary_text") or "").strip()
            if not summary_text:
                return jsonify({"error":"summary_text is required when generate=false"}), 400

        now_ts = int(time.time())
        conn = reports_service._connect()
        _ensure_summaries_table(conn)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO summaries (
                created_at, updated_at, period_start, period_end, date, channel_id,
                author_user_id, title, summary_text, tags, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_ts, now_ts, period_start_ts, period_end_ts, date_label, channel_id,
            author_user_id, title, summary_text, tags, status
        ))
        sid = cur.lastrowid
        conn.commit()
        conn.close()

        return jsonify({"status":"ok","id":sid})
    except Exception as e:
        return jsonify({"status":"error","error":str(e)}), 500

# ---------------------------
# Global Search (insights + sops + summaries)
# ---------------------------

@dashboard_api.get("/search")
@require_dashboard_role("viewer", "user", "admin")
def dashboard_global_search():
    """
    Unified search across insights, SOPs, and summaries.

    Query params:
      - q: free-text query (optional)
      - types: comma-separated subset of insights,sops,summaries (default: all)
      - channel_id: optional filter applied where available
      - status: optional filter (applies to sops/summaries only)
      - start: YYYY-MM-DD (filters by created_at/period_start >= start)
      - end: YYYY-MM-DD (filters by created_at/period_start < end+1 day)
      - limit: cap combined results (default 100, max 200)

    Response:
      { status: "ok", items: [ {type, id, title, text, channel_id, tags, status, date, created_at, ...}, ... ] }
    """
    try:
        q = (request.args.get("q") or "").strip()
        types_raw = (request.args.get("types") or "insights,sops,summaries").lower()
        types = {t.strip() for t in types_raw.split(",") if t.strip()}
        if not types:
            types = {"insights", "sops", "summaries"}

        channel_id = (request.args.get("channel_id") or "").strip() or None
        status = (request.args.get("status") or "").strip() or None
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        limit = max(1, min(200, int(request.args.get("limit") or "100")))

        # Parse date filters
        start_ts = end_ts = None
        if start_str:
            try:
                sdt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                start_ts = int(sdt.timestamp())
            except ValueError:
                return jsonify({"error": "Invalid 'start' format. Use YYYY-MM-DD"}), 400
        if end_str:
            try:
                edt = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
                end_ts = int(edt.timestamp())  # exclusive
            except ValueError:
                return jsonify({"error": "Invalid 'end' format. Use YYYY-MM-DD"}), 400

        conn = reports_service._connect()
        # Ensure tables exist (no-op if already created)
        try:
            _ensure_sops_table(conn)
        except Exception:
            pass
        try:
            _ensure_summaries_table(conn)
        except Exception:
            pass

        cur = conn.cursor()
        items = []

        # ---- Insights ----
        if "insights" in types:
            sql = """
              SELECT id, created_at, date, channel_id, decisions, todos, facts, message_text
              FROM insights
              WHERE 1=1
            """
            params = []
            if q:
                like = f"%{q}%"
                sql += " AND (message_text LIKE ? OR decisions LIKE ? OR todos LIKE ? OR facts LIKE ?)"
                params.extend([like, like, like, like])
            if channel_id:
                sql += " AND channel_id = ?"
                params.append(channel_id)
            if start_ts is not None:
                sql += " AND created_at >= ?"
                params.append(start_ts)
            if end_ts is not None:
                sql += " AND created_at < ?"
                params.append(end_ts)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

            import json as _json
            for r in rows:
                # Build a compact preview from decisions/todos/facts or fallback to message_text
                preview_lines = []
                try:
                    ds = _json.loads(r["decisions"] or "[]")[:3]
                except Exception:
                    ds = []
                try:
                    ts_ = _json.loads(r["todos"] or "[]")[:3]
                except Exception:
                    ts_ = []
                try:
                    fs = _json.loads(r["facts"] or "[]")[:3]
                except Exception:
                    fs = []

                for col in (ds, ts_, fs):
                    for x in col:
                        if x:
                            preview_lines.append(f"- {x}")
                text_preview = "\n".join(preview_lines) or (r["message_text"] or "")[:500]

                items.append({
                    "type": "insight",
                    "id": r["id"],
                    "title": f"Insights {r['date']}",
                    "text": text_preview,
                    "channel_id": r["channel_id"],
                    "tags": None,
                    "status": None,
                    "date": r["date"],
                    "created_at": r["created_at"],
                })

        # ---- SOPs ----
        if "sops" in types:
            sql = """
              SELECT id, created_at, topic AS title, channel_id, tags, status, sop_text
              FROM sops
              WHERE 1=1
            """
            params = []
            if q:
                like = f"%{q}%"
                sql += " AND (topic LIKE ? OR tags LIKE ? OR sop_text LIKE ?)"
                params.extend([like, like, like])
            if channel_id:
                sql += " AND channel_id = ?"
                params.append(channel_id)
            if status:
                sql += " AND status = ?"
                params.append(status)
            # created_at window (if provided)
            if start_ts is not None:
                sql += " AND created_at >= ?"
                params.append(start_ts)
            if end_ts is not None:
                sql += " AND created_at < ?"
                params.append(end_ts)

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            for r in rows:
                items.append({
                    "type": "sop",
                    "id": r["id"],
                    "title": r["title"],
                    "text": (r["sop_text"] or "")[:1000],
                    "channel_id": r["channel_id"],
                    "tags": r["tags"],
                    "status": r["status"],
                    "date": None,
                    "created_at": r["created_at"],
                })

        # ---- Summaries ----
        if "summaries" in types:
            sql = """
              SELECT id, created_at, title, channel_id, tags, status,
                     summary_text, period_start, period_end, date
              FROM summaries
              WHERE 1=1
            """
            params = []
            if q:
                like = f"%{q}%"
                sql += " AND (title LIKE ? OR tags LIKE ? OR summary_text LIKE ?)"
                params.extend([like, like, like])
            if channel_id:
                sql += " AND channel_id = ?"
                params.append(channel_id)
            if status:
                sql += " AND status = ?"
                params.append(status)
            # Prefer filtering by window start if present, else fallback to created_at
            if start_ts is not None:
                sql += " AND (period_start IS NULL OR period_start >= ?)"
                params.append(start_ts)
            if end_ts is not None:
                sql += " AND (period_start IS NULL OR period_start < ?)"
                params.append(end_ts)

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            for r in rows:
                items.append({
                    "type": "summary",
                    "id": r["id"],
                    "title": r["title"],
                    "text": (r["summary_text"] or "")[:1000],
                    "channel_id": r["channel_id"],
                    "tags": r["tags"],
                    "status": r["status"],
                    "date": r["date"],
                    "created_at": r["created_at"],
                    "period_start": r["period_start"],
                    "period_end": r["period_end"],
                })

        conn.close()

        # Combine + sort + cap
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        if len(items) > limit:
            items = items[:limit]

        return jsonify({"status": "ok", "items": items})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ---------------------------
# Auth helper: who am I? (role)
# ---------------------------
@dashboard_api.get("/auth/me")
@require_dashboard_role("viewer","user","admin")
def auth_me():
    #tok = _extract_token_from_request(request)
    #role = resolve_dashboard_role_from_token(tok) or "none"
    #return jsonify({"status": "ok", "role": role})
    role = current_role()  # returns DEFAULT_PUBLIC_ROLE when public mode is on
    return jsonify({"status": "ok", "role": role})

# Register the Dashboard API under /dashboard/api
app.register_blueprint(dashboard_api, url_prefix="/dashboard/api")




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
# Dashboard (static shell)
# ---------------------------

DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard_static")

@app.get("/")
def root_redirect():
    return redirect("/dashboard", code=302)
@app.get("/dashboard")
def dashboard_index_no_slash():
    return send_from_directory(DASHBOARD_DIR, "index.html")
@app.get("/dashboard/")
def dashboard_index_with_slash():
    return send_from_directory(DASHBOARD_DIR, "index.html")
# Serve assets from /dashboard/static/<file>
@app.get("/dashboard/static/<path:filename>")
def dashboard_static(filename):
    return send_from_directory(DASHBOARD_DIR, filename)




# ---------------------------
# Entry Point
# ---------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)