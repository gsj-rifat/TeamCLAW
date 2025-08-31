# report_commands.py
"""
Slack report commands module.

Encapsulates:
- Parsing of in-Slack commands to generate Daily/Weekly reports
- Integration with ReportsService to fetch/aggregate data
- Posting to Slack via an injected callable
- A Flask Blueprint to handle a Slack slash command (/report)

Supported command texts:
  - "report daily"
  - "report daily 2025-09-01"
  - "report weekly"
  - "report weekly 2025-09-01"
  - Add "to here" to post the report into the channel where the command is issued.
    (By default this is the behavior; "to here" is optional and explicit.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Dict, Any

from flask import Blueprint, request, jsonify

from reporting import ReportsService


@dataclass(frozen=True)
class SlackReportCommandsConfig:
    """
    Configuration for the Slack report commands.
    """
    # Optional fallback if a target channel is not provided and we are not in a message context.
    default_post_channel_id: Optional[str] = None


class SlackReportCommandHandler:
    """
    Handler for parsing Slack text commands and generating/posting reports.

    Responsibilities:
    - Parse command text (daily/weekly + optional date)
    - Build the correct time window
    - Fetch & aggregate via ReportsService
    - Generate Slack-formatted text and post to the target channel
    """

    def __init__(
        self,
        service: ReportsService,
        post_to_slack: Callable[[str, str], bool],
        config: SlackReportCommandsConfig,
    ):
        self.service = service
        self.post_to_slack = post_to_slack
        self.config = config

    @staticmethod
    def _parse_iso_date(candidate: str) -> Optional[datetime]:
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _parse_command_text(
        self,
        text: str,
        source_channel_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Parse the command text.
        Expected forms:
          - "report daily [YYYY-MM-DD] [to here]"
          - "report weekly [YYYY-MM-DD] [to here]"

        Returns a dict:
          {
            "kind": "daily"|"weekly",
            "start": datetime (UTC),
            "end": datetime (UTC),
            "target_channel_id": str,
            "filter_channel_id": Optional[str]
          }
        """
        raw = (text or "").strip()
        # Remove leading mention if present (e.g., "<@U123> report daily ...")
        raw = re.sub(r"^<@[^>]+>\s*", "", raw)

        tokens = raw.split()
        if not tokens:
            raise ValueError("Missing command. Try: 'report daily' or 'report weekly'.")

        # Allow both slash command text ("daily ...") and in-channel ("report daily ...")
        if tokens[0].lower() == "report":
            tokens = tokens[1:]

        if not tokens:
            raise ValueError("Missing subcommand. Use 'daily' or 'weekly'.")

        kind = tokens[0].lower()
        if kind not in ("daily", "weekly"):
            raise ValueError("Unknown subcommand. Use 'daily' or 'weekly'.")

        # Defaults
        target_channel_id = source_channel_id or self.config.default_post_channel_id
        filter_channel_id = None
        dt: Optional[datetime] = None

        # Try to parse optional date as the next token, if present
        idx = 1
        if idx < len(tokens):
            maybe_date = self._parse_iso_date(tokens[idx])
            if maybe_date:
                dt = maybe_date
                idx += 1

        # Additional keywords: "to here" (post in the current channel)
        # (You can extend this later to support "for <#C...>" as a filter channel.)
        while idx < len(tokens):
            t = tokens[idx].lower()
            if t == "to":
                # Currently only supporting "to here"
                if idx + 1 < len(tokens) and tokens[idx + 1].lower() == "here":
                    target_channel_id = source_channel_id or target_channel_id
                    idx += 2
                else:
                    # If needed later, parse Slack channel mention format: <#C123|name>
                    # For now, keep it simple and ignore other patterns.
                    idx += 1
            else:
                idx += 1

        if not target_channel_id:
            raise ValueError("No target channel resolved. Try adding 'to here' or set a default.")

        # Resolve time window
        now = datetime.now(timezone.utc)
        if kind == "daily":
            if not dt:
                today = now.date()
                start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
            else:
                start = dt
            end = start + timedelta(days=1)
        else:
            # weekly
            if not dt:
                # Default to current Monday (UTC)
                monday = (now - timedelta(days=now.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                start = monday
            else:
                start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=7)

        return {
            "kind": kind,
            "start": start,
            "end": end,
            "target_channel_id": target_channel_id,
            "filter_channel_id": filter_channel_id,
        }

    def handle_text_command(
        self,
        source_channel_id: str,
        text: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parse the text command, generate the report, and post to Slack.

        Returns:
          {
            "ok": bool,
            "message": str,
            "posted": bool,
            "target_channel_id": str,
            "counts": {"decisions": int, "todos": int, "facts": int},
            "period": "daily"|"weekly",
            "date_or_week_start": "YYYY-MM-DD"
          }
        """
        parsed = self._parse_command_text(text=text, source_channel_id=source_channel_id)

        rows = self.service.fetch_between(
            int(parsed["start"].timestamp()),
            int(parsed["end"].timestamp()),
            parsed["filter_channel_id"],
        )
        aggregates = self.service.build_aggregates(rows)
        period_label = "Daily" if parsed["kind"] == "daily" else "Weekly"
        text_msg = self.service.generate_report_text(
            period_label=period_label,
            start_dt=parsed["start"],
            end_dt=parsed["end"],
            channel_id=parsed["filter_channel_id"] or source_channel_id,
            aggregates=aggregates,
        )

        posted = self.post_to_slack(parsed["target_channel_id"], text_msg)

        return {
            "ok": posted,
            "message": "Report posted." if posted else "Failed to post report.",
            "posted": posted,
            "target_channel_id": parsed["target_channel_id"],
            "counts": {
                "decisions": len(aggregates.get("decisions", [])),
                "todos": len(aggregates.get("todos", [])),
                "facts": len(aggregates.get("facts", [])),
            },
            "period": parsed["kind"],
            "date_or_week_start": parsed["start"].strftime("%Y-%m-%d"),
        }


def create_slash_commands_blueprint(
    handler: SlackReportCommandHandler,
    signature_verifier: callable,
) -> Blueprint:
    """
    Blueprint exposing a Slack slash command endpoint:
      - POST /slack/commands  (configure Slack with /report)

    Slack sends application/x-www-form-urlencoded; we return a quick JSON
    ephemeral acknowledgment and the handler posts to the channel.
    """
    bp = Blueprint("slack_commands", __name__)

    @bp.post("/commands")
    def handle_commands():
        if not signature_verifier(request):
            return jsonify({"error": "Invalid signature"}), 403

        form = request.form or {}
        command = form.get("command", "")
        text = form.get("text", "")  # Slack sends only what's after '/report'
        source_channel_id = form.get("channel_id")
        user_id = form.get("user_id")

        # Normalize to "report ..." so the same parser works for slash and text.
        normalized_text = f"report {text}".strip()

        try:
            result = handler.handle_text_command(
                source_channel_id=source_channel_id,
                text=normalized_text,
                user_id=user_id,
            )
            # Ephemeral response to the user (posting to channel is already done)
            status_line = (
                f"✅ Posted {result['period']} report to <#{result['target_channel_id']}> "
                f"({result['date_or_week_start']}). "
                f"items: decisions={result['counts']['decisions']}, "
                f"todos={result['counts']['todos']}, facts={result['counts']['facts']}."
                if result["posted"] else
                "❌ Failed to post the report. Check bot permissions and channel membership."
            )
            return jsonify({
                "response_type": "ephemeral",
                "text": status_line,
            })
        except ValueError as ve:
            return jsonify({
                "response_type": "ephemeral",
                "text": f"⚠️ {ve}\nTry: '/report daily [YYYY-MM-DD]' or '/report weekly [YYYY-MM-DD]'. "
                        "Add 'to here' to post in this channel.",
            })

    return bp