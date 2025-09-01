# sop_readiness.py
# -*- coding: utf-8 -*-
"""
SOP Readiness / Conversation Completeness Module

Purpose
- Analyze recent conversation context for a topic to determine if it is "complete" for SOP drafting.
- If incomplete, generate a Slack-friendly clarification prompt enumerating missing details.

Design
- Non-invasive: integrates with existing ReportsService and Groq client.
- Reusable: expose a small service API, plus a Flask blueprint for REST usage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Callable

from flask import Blueprint, request, jsonify
from reporting import ReportsService


@dataclass(frozen=True)
class SopReadinessConfig:
    # How many days of context to analyze if not explicitly provided
    default_days: int = 14
    # Cap the total number of items sent as context (keeps prompts efficient)
    max_context_items: int = 60
    # Default Slack channel used if posting and no explicit channel provided
    default_post_channel_id: Optional[str] = None
    # Model name for the Groq chat completions call
    model_name: str = "llama-3.3-70b-versatile"


class SopReadinessService:
    """
    Service that:
      1) Gathers recent context for a topic from ReportsService.
      2) Uses Groq LLM to judge if conversation is complete for SOP drafting.
      3) When incomplete, generates a targeted clarification prompt.

    Returns structured results suitable for Slack and APIs.
    """

    def __init__(
        self,
        reports: ReportsService,
        groq_client,  # expects chat.completions.create(...)
        config: SopReadinessConfig,
    ):
        self.reports = reports
        self.groq = groq_client
        self.config = config

    def _collect_context(
        self,
        topic: str,
        channel_id: Optional[str],
        days: Optional[int],
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        window_days = int(days or self.config.default_days)
        start = now - timedelta(days=max(1, window_days))

        rows = self.reports.fetch_between(
            int(start.timestamp()),
            int(now.timestamp()),
            channel_id=channel_id,
        )

        topic_lc = (topic or "").strip().lower()

        decisions: List[str] = []
        todos: List[str] = []
        facts: List[str] = []
        messages: List[str] = []

        for r in rows:
            try:
                d = json.loads(r["decisions"] or "[]")
                t = json.loads(r["todos"] or "[]")
                f = json.loads(r["facts"] or "[]")
            except Exception:
                d, t, f = [], [], []

            msg = (r["message_text"] or "").strip()

            if topic_lc:
                # Prefer topic-matching items; if none match, include other context to avoid starvation
                d_topic = [x for x in d if topic_lc in x.lower()]
                t_topic = [x for x in t if topic_lc in x.lower()]
                f_topic = [x for x in f if topic_lc in x.lower()]
                if topic_lc in (msg.lower()):
                    messages.append(msg)

                decisions.extend(d_topic or d)
                todos.extend(t_topic or t)
                facts.extend(f_topic or f)
            else:
                decisions.extend(d)
                todos.extend(t)
                facts.extend(f)
                if msg:
                    messages.append(msg)

        # Deduplicate, preserve order
        def uniq(items: List[str]) -> List[str]:
            seen = set()
            out: List[str] = []
            for it in items:
                key = (it or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(key)
            return out

        decisions = uniq(decisions)
        todos = uniq(todos)
        facts = uniq(facts)
        messages = uniq(messages)

        # Balance truncation
        cap = max(10, self.config.max_context_items)
        share = max(5, cap // 4)
        decisions = decisions[:share]
        todos = todos[:share]
        facts = facts[:share]
        messages = messages[:share]

        return {
            "start": start,
            "end": now,
            "decisions": decisions,
            "todos": todos,
            "facts": facts,
            "messages": messages,
        }

    def _build_llm_prompt(self, topic: str, ctx: Dict[str, Any]) -> str:
        def block(title: str, items: List[str]) -> str:
            if not items:
                return f"{title}:\n- (none)\n"
            return f"{title}:\n" + "\n".join(f"- {x}" for x in items) + "\n"

        ctx_str = "\n".join([
            f"Time Window (UTC): {ctx['start'].strftime('%Y-%m-%d')} → {ctx['end'].strftime('%Y-%m-%d')}",
            block("Recent Decisions", ctx.get("decisions", [])),
            block("Recent To-Dos", ctx.get("todos", [])),
            block("Recent Facts", ctx.get("facts", [])),
            block("Notable Messages", ctx.get("messages", [])),
        ])

        # The LLM must return strict JSON we can parse.
        return f"""
You are an operations analyst. Determine if the discussion on the topic is complete enough
to draft a high-quality SOP without further clarification.

Topic: "{topic}"

Context (use only what is provided, do not invent facts):
{ctx_str}

Return ONLY a JSON object in this exact schema:
{{
  "is_complete": true|false,
  "reason": "brief explanation",
  "missing_fields": [
    "short bullet describing a missing detail",
    "... additional bullets"
  ],
  "clarification_prompt": "If is_complete=false, provide a concise Slack-friendly prompt that asks the team for the missing details. If complete, provide an empty string."
}}
"""
    def assess_readiness(
        self,
        topic: str,
        channel_id: Optional[str],
        days: Optional[int] = None,
        temperature: float = 0.1,
        max_tokens: int = 600,
    ) -> Dict[str, Any]:
        """
        Core API: returns structure describing completeness and a prompt if incomplete.
        """
        if not self.groq:
            # Fail-safe: assume incomplete if we can't reason automatically
            return {
                "topic": topic,
                "channel_filter": channel_id,
                "window_days": int(days or self.config.default_days),
                "is_complete": False,
                "reason": "LLM unavailable; cannot verify completeness.",
                "missing_fields": ["Please rerun when the LLM is available."],
                "clarification_prompt": f"To finalize the SOP for '{topic}', please provide goals, scope, responsible roles, tools/systems, and the end-to-end steps with acceptance criteria.",
                "window_start": "",
                "window_end": "",
                "context_counts": {"decisions": 0, "todos": 0, "facts": 0, "messages": 0},
            }

        ctx = self._collect_context(topic=topic, channel_id=channel_id, days=days)
        prompt = self._build_llm_prompt(topic, ctx)

        try:
            resp = self.groq.chat.completions.create(
                model=self.config.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            # Conservative default: request clarification
            return {
                "topic": topic,
                "channel_filter": channel_id,
                "window_days": int(days or self.config.default_days),
                "is_complete": False,
                "reason": f"LLM error: {e}",
                "missing_fields": ["Provide goals, scope, roles, tools, and detailed steps."],
                "clarification_prompt": f"To complete the SOP for '{topic}', please share goals, scope, roles, tools/systems, and numbered steps including acceptance checks.",
                "window_start": ctx["start"].strftime("%Y-%m-%d"),
                "window_end": ctx["end"].strftime("%Y-%m-%d"),
                "context_counts": {
                    "decisions": len(ctx["decisions"]),
                    "todos": len(ctx["todos"]),
                    "facts": len(ctx["facts"]),
                    "messages": len(ctx["messages"]),
                },
            }

        # Strict JSON parsing, tolerant of extra text fences
        def extract_json(s: str) -> Dict[str, Any]:
            import re, json as _json
            t = s.strip()
            if t.startswith("```"):
                t = re.sub(r"^```(?:json)?\\s*", "", t, flags=re.IGNORECASE)
                t = re.sub(r"\\s*```$", "", t)
            try:
                return _json.loads(t)
            except Exception:
                # fallback: find first {...}
                start = t.find("{")
                if start == -1:
                    raise ValueError("No JSON object found")
                depth = 0
                for i in range(start, len(t)):
                    ch = t[i]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            return _json.loads(t[start:i+1])
                raise ValueError("Unbalanced JSON")

        try:
            parsed = extract_json(raw)
        except Exception as e:
            # Fallback prompt if parsing fails
            parsed = {
                "is_complete": False,
                "reason": f"Could not parse LLM output: {e}",
                "missing_fields": ["Provide goals, scope, roles, tools, steps."],
                "clarification_prompt": f"To complete the SOP for '{topic}', please provide goals, scope, roles, tools, and numbered steps.",
            }

        result = {
            "topic": topic,
            "channel_filter": channel_id,
            "window_days": int(days or self.config.default_days),
            "is_complete": bool(parsed.get("is_complete", False)),
            "reason": str(parsed.get("reason", ""))[:500],
            "missing_fields": list(parsed.get("missing_fields", []))[:20],
            "clarification_prompt": str(parsed.get("clarification_prompt", ""))[:2000],
            "window_start": ctx["start"].strftime("%Y-%m-%d"),
            "window_end": ctx["end"].strftime("%Y-%m-%d"),
            "context_counts": {
                "decisions": len(ctx["decisions"]),
                "todos": len(ctx["todos"]),
                "facts": len(ctx["facts"]),
                "messages": len(ctx["messages"]),
            },
        }
        return result


def create_sop_readiness_blueprint(
    service: SopReadinessService,
    post_to_slack: Callable[[str, str], bool],
) -> Blueprint:
    """
    Blueprint exposing:
      - GET /sop/readiness?topic=...&channel_id=...&days=...&post=true&target_channel_id=...
    """
    bp = Blueprint("sop_readiness", __name__)

    def _parse_bool(v: Optional[str], default: bool = False) -> bool:
        if v is None:
            return default
        return str(v).lower() in {"1", "true", "yes", "y", "on"}

    @bp.get("/readiness")
    def readiness_endpoint():
        topic = (request.args.get("topic") or "").strip()
        if not topic:
            return jsonify({"error": "Missing 'topic'"}), 400

        channel_id = request.args.get("channel_id")
        days = request.args.get("days")
        days_int = int(days) if days and days.isdigit() else None

        post = _parse_bool(request.args.get("post"), False)
        target_channel = request.args.get("target_channel_id")

        try:
            res = service.assess_readiness(topic=topic, channel_id=channel_id, days=days_int)
            # Optionally post the clarification prompt if incomplete
            posted = False
            if post and not res.get("is_complete", False):
                dest = target_channel or service.config.default_post_channel_id or channel_id
                if dest and res.get("clarification_prompt"):
                    posted = bool(post_to_slack(dest, f"🧭 *SOP Readiness Check: {res['topic']}*\n\n{res['clarification_prompt']}"))
            return jsonify({**res, "posted": posted, "target_channel_id": target_channel})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return bp