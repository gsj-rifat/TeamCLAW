NOISE_FILTER_PROMPT = """
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

EXTRACTION_PROMPT = """
Extract insights from this message and respond with ONLY a JSON object:

Message: "{text}"

Required JSON format (no other text):
{{
    "decisions": [{{"text": "decision made"}}], 
    "todos": [{{"text": "action item"}}], 
    "facts": [{{"text": "key fact"}}]
}}
"""

REPORT_SUMMARY_PROMPT = """
You are an expert note-taker. Write a concise, executive-friendly summary (120–180 words)
for the window {start_date} -> {end_date}
titled: "{title}".

Ground ONLY in these items. Prefer synthesis over copying.

Decisions:
{decisions}

To-Dos:
{todos}

Facts:
{facts}

Output plain text suitable for Slack (no headers, no JSON).
"""
