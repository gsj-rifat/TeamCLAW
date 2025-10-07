# sop_generator.py
# -*- coding: utf-8 -*-
"""
SOP generation module for AI Shadow Coach.

Adds the ability to generate a Standard Operating Procedure (SOP) from recent
channel context and topic instructions, triggered via:
  - Slack slash command: /sop <topic> [--days N] [to here]
  - In-channel mentions: "@Bot create sop for <topic>" or "sop <topic>"
  - REST: GET /sop/generate?topic=...&channel_id=...&days=...&post=true

Design goals:
- Keep existing behavior intact (reporting, events)
- Encapsulate SOP logic in a reusable, documented service
- Minimal integration changes in main.py
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Dict, Any, List

from flask import Blueprint, request, jsonify

from reporting import ReportsService


@dataclass(frozen=True)
class SopConfig:
    """
    Configuration for the SOP subsystem.
    """
    default_days: int = 14
    max_context_items: int = 60  # overall cap across decisions/todos/facts/messages
    default_post_channel_id: Optional[str] = None
    model_name: str = "llama-3.3-70b-versatile"  # fallback if not provided during init


class SopService:
    """
    Service that compiles recent context from ReportsService and uses a Groq client
    to generate a structured SOP for a given topic, optionally filtered by channel.

    Responsibilities:
    - Collect context window from SQLite (decisions/todos/facts/messages)
    - Build a high-quality prompt for SOP generation
    - Call Groq to produce a Slack-friendly SOP
    - Optionally post to Slack via an injected function
    """

    def __init__(
        self,
        reports_service: ReportsService,
        groq_client,  # expects a 'chat.completions.create(...)' interface
        post_to_slack: Callable[[str, str], bool],
        config: SopConfig,
    ):
        self.reports = reports_service
        self.groq = groq_client
        self.post_to_slack = post_to_slack
        self.config = config

    def _collect_context(
        self,
        topic: str,
        channel_id: Optional[str],
        days: int,
    ) -> Dict[str, Any]:
        """
        Pulls recent rows from the DB and assembles a compact context block.
        Prioritizes items that mention the topic, but will include general context
        up to max_context_items.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=max(1, days))
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

            # If topic specified, prefer items containing the topic
            if topic_lc:
                d_topic = [x for x in d if topic_lc in x.lower()]
                t_topic = [x for x in t if topic_lc in x.lower()]
                f_topic = [x for x in f if topic_lc in x.lower()]
                if topic_lc in msg.lower():
                    messages.append(msg)

                # Fall back to all if topic matches are sparse
                decisions.extend(d_topic or d)
                todos.extend(t_topic or t)
                facts.extend(f_topic or f)
            else:
                decisions.extend(d)
                todos.extend(t)
                facts.extend(f)
                if msg:
                    messages.append(msg)

        # Deduplicate while preserving order
        def _uniq(seq: List[str]) -> List[str]:
            seen = set()
            out: List[str] = []
            for s in seq:
                s = (s or "").strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                out.append(s)
            return out

        decisions = _uniq(decisions)
        todos = _uniq(todos)
        facts = _uniq(facts)
        messages = _uniq(messages)

        # Trim to max_context_items across all sources (balanced)
        cap = max(10, self.config.max_context_items)
        each_cap = max(5, cap // 4)
        decisions = decisions[:each_cap]
        todos = todos[:each_cap]
        facts = facts[:each_cap]
        messages = messages[:each_cap]

        return {
            "start": start,
            "end": now,
            "decisions": decisions,
            "todos": todos,
            "facts": facts,
            "messages": messages,
        }

    def _build_prompt(self, topic: str, context: Dict[str, Any]) -> str:
        """
        Build a robust SOP prompt that yields a Slack/Markdown-formatted SOP.
        """
        def block(title: str, items: List[str]) -> str:
            if not items:
                return f"{title}:\n- (none found)\n"
            lines = "\n".join(f"- {x}" for x in items)
            return f"{title}:\n{lines}\n"

        ctx_str = "\n".join([
            f"Time Window (UTC): {context['start'].strftime('%Y-%m-%d')} → {context['end'].strftime('%Y-%m-%d')}",
            block("Recent Decisions", context.get("decisions", [])),
            block("Recent To-Dos", context.get("todos", [])),
            block("Recent Facts", context.get("facts", [])),
            block("Notable Messages", context.get("messages", [])),
        ])

        # The model will output a clean Slack-friendly SOP with clear sections.
        return f"""
You are an expert operations writer. Create a concise, implementation-ready SOP in Markdown for the topic below,
grounded in the provided Slack context. Be precise, actionable, and unambiguous.

Topic: "{topic}"

Context (use only if relevant, do not invent details):
{ctx_str}

SOP requirements:
- Title: "SOP: <topic>"
- Purpose (1–3 sentences)
- Scope (what’s in/out)
- Prerequisites (roles, tools, access)
- Roles & Responsibilities (who does what)
- Tools/Systems (links as placeholders if unknown)
- Procedure (numbered steps, include decision points, expected outputs)
- Quality Checks (acceptance criteria, sign-off)
- Troubleshooting (common issues + resolutions)
- References (links or document names, if present in context)
- Versioning (Created on <YYYY-MM-DD>, Owner: <TBD>)

Style:
- Use Slack-friendly Markdown
- Keep it succinct but complete
- Use imperative voice for steps
- Do not include any JSON or extra commentary—only the SOP content
"""

    def generate_sop_text(
        self,
        topic: str,
        channel_id: Optional[str],
        days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate the SOP text from recent context. Returns a dict with SOP and meta.
        """
        if not self.groq:
            raise RuntimeError("Groq client is not configured")

        days = int(days or self.config.default_days)
        context = self._collect_context(topic=topic, channel_id=channel_id, days=days)
        prompt = self._build_prompt(topic, context)

        try:
            resp = self.groq.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.config.model_name,
                temperature=0.2,
                max_tokens=1200,
            )
            sop_text = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            raise RuntimeError(f"GROQ SOP generation failed: {e}")

        return {
            "topic": topic,
            "channel_filter": channel_id,
            "days": days,
            "sop_text": sop_text,
            "context_counts": {
                "decisions": len(context["decisions"]),
                "todos": len(context["todos"]),
                "facts": len(context["facts"]),
                "messages": len(context["messages"]),
            },
            "window_start": context["start"].strftime("%Y-%m-%d"),
            "window_end": context["end"].strftime("%Y-%m-%d"),
        }

    def create_and_optionally_post(
        self,
        topic: str,
        source_channel_id: Optional[str],
        days: Optional[int],
        post_channel_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method: generate SOP and optionally post to Slack.
        """
        result = self.generate_sop_text(topic=topic, channel_id=source_channel_id, days=days)
        posted = False
        target = post_channel_id or self.config.default_post_channel_id or source_channel_id
        if target:
            posted = bool(self.post_to_slack(target, f"📘 *SOP: {result['topic']}*\n\n{result['sop_text']}"))


        return {**result, "posted": posted, "target_channel_id": target}


class SlackSopCommandHandler:
    """
    Parser/handler for SOP Slack commands and in-channel triggers.

    Supported forms (examples):
      - "sop deploy to staging [--days 14] [to here]"
      - "create sop for onboarding flow [--days 21]"
      - "<@Bot> sop incident response --days 30"
    """

    CMD_PATTERNS = [
        r"^\s*sop\s+(?P<topic>.+)$",
        r"^\s*create\s+sop\s+for\s+(?P<topic>.+)$",
        r"^\s*create\s+sop\s+(?P<topic>.+)$",
        r"^\s*make\s+sop\s+for\s+(?P<topic>.+)$",
        r"^\s*make\s+sop\s+(?P<topic>.+)$",
    ]

    def __init__(self, sop_service: SopService):
        self.sop_service = sop_service

    @staticmethod
    def _strip_mention(text: str) -> str:
        return re.sub(r"^<@[^>]+>\s*", "", text or "")

    def _parse(self, text: str, source_channel_id: Optional[str]) -> Dict[str, Any]:
        raw = self._strip_mention(text).strip()

        # Extract optional flags first: --days N, "to here"
        days = None
        target_here = False

        # Normalize flags
        # --days 14
        m = re.search(r"--days\s+(\d{1,3})", raw, flags=re.IGNORECASE)
        if m:
            try:
                days = int(m.group(1))
                raw = raw[:m.start()] + raw[m.end():]
            except Exception:
                pass

        # to here
        if re.search(r"\bto\s+here\b", raw, flags=re.IGNORECASE):
            target_here = True
            raw = re.sub(r"\bto\s+here\b", "", raw, flags=re.IGNORECASE)

        # Match one of the supported topic patterns
        topic = None
        for pat in self.CMD_PATTERNS:
            mm = re.match(pat, raw, flags=re.IGNORECASE)
            if mm and mm.group("topic"):
                topic = mm.group("topic").strip()
                break

        if not topic:
            raise ValueError(
                "Invalid SOP command. Try: 'sop <topic> [--days N] [to here]' "
                "or 'create sop for <topic>'."
            )

        target_channel_id = source_channel_id if target_here else None

        return {
            "topic": topic,
            "days": days,
            "target_channel_id": target_channel_id,
            "source_channel_id": source_channel_id,
        }

    def handle_text_command(
        self,
        text: str,
        source_channel_id: Optional[str],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = self._parse(text, source_channel_id)
        result = self.sop_service.create_and_optionally_post(
            topic=parsed["topic"],
            source_channel_id=parsed["source_channel_id"],
            days=parsed["days"],
            post_channel_id=parsed["target_channel_id"],
        )
        return {
            "ok": True,
            "posted": result["posted"],
            "target_channel_id": result["target_channel_id"],
            "topic": result["topic"],
            "days": result["days"],
            "context_counts": result["context_counts"],
            "window": {"start": result["window_start"], "end": result["window_end"]},
        }


def create_sop_blueprint(
    sop_handler: SlackSopCommandHandler,
    signature_verifier: callable,
) -> Blueprint:
    """
    Blueprint exposing:
      - POST /sop/commands   (configure Slack with /sop)
      - GET  /sop/generate   (programmatic trigger)
    """
    bp = Blueprint("sop", __name__)

    @bp.post("/commands")
    def slash_command():
        # Slack slash command endpoint for /sop
        if not signature_verifier(request):
            return jsonify({"error": "Invalid signature"}), 403

        form = request.form or {}
        command = form.get("command", "").strip().lower()
        text = form.get("text", "")  # what's after '/sop'
        source_channel_id = form.get("channel_id")
        user_id = form.get("user_id")

        # Only accept /sop here (keep /report in its own blueprint)
        if command != "/sop":
            return jsonify({"response_type": "ephemeral", "text": "Unsupported command."})

        try:
            result = sop_handler.handle_text_command(
                text=text,
                source_channel_id=source_channel_id,
                user_id=user_id,
            )
            status_line = (
                f"📘 Generated SOP for '{result['topic']}' "
                f"(window {result['window']['start']} → {result['window']['end']}, "
                f"days={result['days']}). "
                + ("Posted to this channel." if result["posted"] else "Not posted (no channel resolved).")
            )
            return jsonify({"response_type": "ephemeral", "text": status_line})
        except ValueError as ve:
            return jsonify({"response_type": "ephemeral", "text": f"⚠️ {ve}"})
        except Exception as e:
            return jsonify({"response_type": "ephemeral", "text": f"❌ SOP generation failed: {e}"}), 500

    @bp.get("/generate")
    def generate_rest():
        """
        REST trigger:
          - topic=<required>
          - channel_id=<optional; filter/anchor for context>
          - days=<optional; default from config>
          - post=true|false
          - target_channel_id=<optional>
        """
        topic = (request.args.get("topic") or "").strip()
        if not topic:
            return jsonify({"error": "Missing 'topic' query param"}), 400

        channel_id = request.args.get("channel_id")
        try:
            days = int(request.args.get("days")) if request.args.get("days") else None
        except Exception:
            return jsonify({"error": "Invalid 'days' value"}), 400

        post = str(request.args.get("post", "false")).lower() in {"1", "true", "yes", "y", "on"}
        target_channel_id = request.args.get("target_channel_id")

        try:
            if post:
                res = sop_handler.sop_service.create_and_optionally_post(
                    topic=topic,
                    source_channel_id=channel_id,
                    days=days,
                    post_channel_id=target_channel_id,
                )
            else:
                res = sop_handler.sop_service.generate_sop_text(
                    topic=topic,
                    channel_id=channel_id,
                    days=days,
                )
                res["posted"] = False
                res["target_channel_id"] = target_channel_id

            return jsonify({"status": "ok", **res})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    return bp