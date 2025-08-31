# reporting.py
# -*- coding: utf-8 -*-
"""
Reporting module for AI Shadow Coach.

Encapsulates:
- SQLite persistence for extracted insights
- Aggregation utilities for daily/weekly reports
- Human-readable report text generation
- A Flask Blueprint exposing /reports/daily and /reports/weekly

Usage:
    from reporting import ReportsService, create_reports_blueprint
    service = ReportsService(db_path="insights.db")
    app.register_blueprint(
        create_reports_blueprint(
            service,
            default_post_channel_id="C123",
            post_to_slack=post_to_slack_channel
        ),
        url_prefix="/reports"
    )
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Any

from flask import Blueprint, jsonify, request


@dataclass(frozen=True)
class ReportsConfig:
    """Configuration values for the reporting subsystem."""
    db_path: str = "insights.db"
    include_facts: bool = True
    max_items: int = 50
    # Used when endpoints are called with post=true and no target_channel_id is provided.
    default_post_channel_id: Optional[str] = None


class ReportsService:
    """
    Service for storing insights and generating time-based reports.

    Responsibilities:
    - Initialize and maintain a lightweight SQLite database
    - Persist extracted insights (decisions/todos/facts)
    - Fetch and aggregate insights across time windows
    - Generate readable Slack-friendly report text
    """

    def __init__(self, config: ReportsConfig):
        self.config = config
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.config.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create the insights table if it does not exist."""
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    channel_id TEXT,
                    user_id TEXT,
                    decisions TEXT,
                    todos TEXT,
                    facts TEXT,
                    message_text TEXT
                );
                """
            )
            conn.commit()
            conn.close()
            print(f"✅ SQLite initialized at {self.config.db_path}")
        except Exception as exc:
            print(f"❌ SQLite init error: {exc}")

    def save_insights(
        self,
        channel_id: str,
        user_id: str,
        message_text: str,
        insights: Dict[str, Any],
    ) -> None:
        """
        Persist insights for later aggregation.

        Skips insert if no decisions/todos/facts are present.
        """
        if not any(insights.get(k) for k in ("decisions", "todos", "facts")):
            return

        try:
            now = datetime.now(timezone.utc)
            row = (
                int(now.timestamp()),
                now.strftime("%Y-%m-%d"),
                channel_id or "",
                user_id or "",
                json.dumps(insights.get("decisions", []) or []),
                json.dumps(insights.get("todos", []) or []),
                json.dumps(insights.get("facts", []) or []),
                message_text or "",
            )
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO insights (
                    created_at, date, channel_id, user_id,
                    decisions, todos, facts, message_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                row,
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            print(f"❌ SQLite save_insights error: {exc}")

    def fetch_between(
        self,
        start_ts: int,
        end_ts: int,
        channel_id: Optional[str] = None,
    ) -> List[sqlite3.Row]:
        """Fetch raw insight rows between timestamps [start_ts, end_ts)."""
        try:
            conn = self._connect()
            cur = conn.cursor()
            if channel_id:
                cur.execute(
                    """
                    SELECT * FROM insights
                    WHERE created_at >= ? AND created_at < ? AND channel_id = ?
                    ORDER BY created_at ASC
                    """,
                    (start_ts, end_ts, channel_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM insights
                    WHERE created_at >= ? AND created_at < ?
                    ORDER BY created_at ASC
                    """,
                    (start_ts, end_ts),
                )
            rows = cur.fetchall()
            conn.close()
            return rows
        except Exception as exc:
            print(f"❌ SQLite fetch_between error: {exc}")
            return []

    @staticmethod
    def _unique_preserve_order(items: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for it in items:
            if not it:
                continue
            key = it.strip()
            if key not in seen:
                seen.add(key)
                out.append(key)
        return out

    def build_aggregates(self, rows: List[sqlite3.Row]) -> Dict[str, List[str]]:
        """
        Build aggregated lists of decisions, todos, and facts.
        Duplicates are removed while preserving encounter order.
        """
        decisions: List[str] = []
        todos: List[str] = []
        facts: List[str] = []

        for r in rows:
            try:
                decisions.extend(json.loads(r["decisions"] or "[]"))
                todos.extend(json.loads(r["todos"] or "[]"))
                facts.extend(json.loads(r["facts"] or "[]"))
            except Exception:
                continue

        return {
            "decisions": self._unique_preserve_order(decisions)[: self.config.max_items],
            "todos": self._unique_preserve_order(todos)[: self.config.max_items],
            "facts": self._unique_preserve_order(facts)[: self.config.max_items],
        }

    def generate_report_text(
        self,
        period_label: str,
        start_dt: datetime,
        end_dt: datetime,
        channel_id: Optional[str],
        aggregates: Dict[str, List[str]],
    ) -> str:
        """
        Create a Slack-friendly report message from aggregates.
        """
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = (end_dt - timedelta(seconds=1)).strftime("%Y-%m-%d")
        header = f"🗓️ *{period_label} Report* ({start_str} → {end_str}, UTC)"
        if channel_id:
            header += f" — Channel: <#{channel_id}>"

        lines = [header, ""]

        if aggregates.get("decisions"):
            lines.append(f"⚡ *Decisions* ({len(aggregates['decisions'])}):")
            lines.extend([f"• {d}" for d in aggregates["decisions"]])
            lines.append("")

        if aggregates.get("todos"):
            lines.append(f"📋 *To-Dos* ({len(aggregates['todos'])}):")
            lines.extend([f"• {t}" for t in aggregates["todos"]])
            lines.append("")

        if self.config.include_facts and aggregates.get("facts"):
            lines.append(f"💡 *Facts* ({len(aggregates['facts'])}):")
            lines.extend([f"• {f}" for f in aggregates["facts"]])
            lines.append("")

        if not any(aggregates.get(k) for k in ("decisions", "todos", "facts")):
            lines.append("_No insights collected for this period._")

        return "\n".join(lines)


def create_reports_blueprint(
    service: ReportsService,
    default_post_channel_id: Optional[str],
    post_to_slack: Callable[[str, str], bool],
) -> Blueprint:
    """
    Factory that returns a Flask Blueprint exposing:
      - GET /reports/daily
      - GET /reports/weekly

    Both endpoints support:
      - channel_id: filter on a Slack channel
      - post: true|false (default: false) — will post the report to Slack
      - target_channel_id: override the default Slack channel for posting
    """

    bp = Blueprint("reports", __name__)

    def _parse_bool(v: Optional[str], default: bool = False) -> bool:
        if v is None:
            return default
        return str(v).lower() in {"1", "true", "yes", "y", "on"}

    @bp.get("/daily")
    def daily_report():
        """
        date=YYYY-MM-DD (UTC) - defaults to today
        channel_id=...
        post=true|false (default false)
        target_channel_id=... (optional)
        """
        date_str = request.args.get("date")
        channel_id = request.args.get("channel_id")
        post = _parse_bool(request.args.get("post"), False)
        target_channel = (
            request.args.get("target_channel_id") or default_post_channel_id
        )

        # Resolve start/end for the day in UTC
        if date_str:
            try:
                start = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        else:
            today = datetime.now(timezone.utc).date()
            start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

        end = start + timedelta(days=1)

        rows = service.fetch_between(int(start.timestamp()), int(end.timestamp()), channel_id)
        aggregates = service.build_aggregates(rows)
        text = service.generate_report_text("Daily", start, end, channel_id, aggregates)

        posted = False
        if post:
            if not target_channel:
                return jsonify({"error": "No target channel configured"}), 400
            posted = bool(post_to_slack(target_channel, text))

        return jsonify(
            {
                "status": "ok",
                "period": "daily",
                "date": start.strftime("%Y-%m-%d"),
                "channel_filter": channel_id,
                "counts": {
                    k: len(aggregates.get(k, [])) for k in ("decisions", "todos", "facts")
                },
                "posted": posted,
                "target_channel": target_channel,
                "report_text": text,
            }
        )

    @bp.get("/weekly")
    def weekly_report():
        """
        week_start=YYYY-MM-DD (UTC Monday) - defaults to current week's Monday
        channel_id=...
        post=true|false (default false)
        target_channel_id=... (optional)
        """
        week_start_str = request.args.get("week_start")
        channel_id = request.args.get("channel_id")
        post = _parse_bool(request.args.get("post"), False)
        target_channel = (
            request.args.get("target_channel_id") or default_post_channel_id
        )

        # Resolve start/end for the week (7 days) in UTC
        if week_start_str:
            try:
                ws = datetime.strptime(week_start_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                return jsonify(
                    {"error": "Invalid week_start format. Use YYYY-MM-DD"}
                ), 400
        else:
            now = datetime.now(timezone.utc)
            monday = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            ws = monday

        start = ws
        end = start + timedelta(days=7)

        rows = service.fetch_between(int(start.timestamp()), int(end.timestamp()), channel_id)
        aggregates = service.build_aggregates(rows)
        text = service.generate_report_text("Weekly", start, end, channel_id, aggregates)

        posted = False
        if post:
            if not target_channel:
                return jsonify({"error": "No target channel configured"}), 400
            posted = bool(post_to_slack(target_channel, text))

        return jsonify(
            {
                "status": "ok",
                "period": "weekly",
                "week_start": start.strftime("%Y-%m-%d"),
                "channel_filter": channel_id,
                "counts": {
                    k: len(aggregates.get(k, [])) for k in ("decisions", "todos", "facts")
                },
                "posted": posted,
                "target_channel": target_channel,
                "report_text": text,
            }
        )

    return bp