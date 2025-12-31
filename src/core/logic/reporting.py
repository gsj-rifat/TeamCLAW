from datetime import datetime, timedelta
from typing import List, Dict, Optional
from src.core.interfaces.db import DatabasePort
from src.core.interfaces.llm import LLMProvider
from src.core.models.insights import InsightRecord
from src.infrastructure.prompts import REPORT_SUMMARY_PROMPT

class ReportBuilder:
    def __init__(self, db: DatabasePort, llm: Optional[LLMProvider] = None):
        self.db = db
        self.llm = llm

    async def generate_daily_report(self, date: datetime, channel_id: Optional[str] = None) -> str:
        start_ts = int(date.timestamp())
        end_ts = int((date + timedelta(days=1)).timestamp())
        
        insights = await self.db.fetch_insights(start_ts, end_ts, channel_id)
        return await self._format_report(f"Daily Report ({date.date()})", insights, date, date + timedelta(days=1))

    async def generate_weekly_report(self, start_date: datetime, channel_id: Optional[str] = None) -> str:
        start_ts = int(start_date.timestamp())
        end_date = start_date + timedelta(days=7)
        end_ts = int(end_date.timestamp())

        insights = await self.db.fetch_insights(start_ts, end_ts, channel_id)
        return await self._format_report(f"Weekly Report (Week of {start_date.date()})", insights, start_date, end_date)

    async def _format_report(self, title: str, insights: List[InsightRecord], start: datetime, end: datetime) -> str:
        if not insights:
            return f"🗓️ *{title}*\n_No insights collected._"

        # Aggregate
        all_decisions = []
        all_todos = []
        all_facts = []
        for i in insights:
            all_decisions.extend(i.decisions)
            all_todos.extend(i.todos)
            all_facts.extend(i.facts)
        
        # Deduplicate
        all_decisions = list(dict.fromkeys(all_decisions))
        all_todos = list(dict.fromkeys(all_todos))
        all_facts = list(dict.fromkeys(all_facts))

        # Summarize with LLM if available
        if self.llm:
            prompt = REPORT_SUMMARY_PROMPT.format(
                title=title,
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
                decisions="\n".join(f"- {d}" for d in all_decisions),
                todos="\n".join(f"- {t}" for t in all_todos),
                facts="\n".join(f"- {f}" for f in all_facts)
            )
            try:
                summary = await self.llm.generate_text(prompt)
                return f"🗓️ *{title}*\n\n{summary}"
            except Exception as e:
                print(f"Summary generation failed: {e}")

        # Fallback formatting
        lines = [f"🗓️ *{title}*"]
        if all_decisions:
            lines.append(f"\n⚡ *Decisions*:")
            lines.extend([f"• {d}" for d in all_decisions])
        if all_todos:
            lines.append(f"\n📋 *Todos*:")
            lines.extend([f"• {t}" for t in all_todos])
        if all_facts:
            lines.append(f"\n💡 *Facts*:")
            lines.extend([f"• {f}" for f in all_facts])
            
        return "\n".join(lines)
