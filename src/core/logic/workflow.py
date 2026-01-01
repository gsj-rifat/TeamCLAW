from datetime import datetime
from typing import Optional
from src.core.interfaces.db import DatabasePort
from src.core.interfaces.tickets import TicketProvider
from src.core.interfaces.messaging import NotificationProvider
from src.core.logic.extraction import InsightExtractor
from src.core.models.insights import InsightRecord
from src.infrastructure.config import settings

class MessageWorkflow:
    def __init__(self, 
                 extractor: InsightExtractor, 
                 db: DatabasePort, 
                 jira: TicketProvider, 
                 slack: NotificationProvider):
        self.extractor = extractor
        self.db = db
        self.jira = jira
        self.slack = slack

    async def process_message(self, text: str, channel_id: str, user_id: str, ts: str) -> None:
        # 1. Noise Filter
        meaningful, reason = await self.extractor.is_meaningful(text)
        if not meaningful:
            print(f"Skipping message: {reason}")
            return

        # 2. Extract Insights
        insights = await self.extractor.extract(text)
        
        # 3. Save to DB
        record = InsightRecord(
            tenant_id=settings.default_tenant_id,  # TODO: real context
            created_at=int(datetime.now().timestamp()),
            date=datetime.now().strftime("%Y-%m-%d"),
            channel_id=channel_id,
            slack_user_id=user_id,  # Correct mapping: user_id arg is Slack ID
            decisions=[d.text for d in insights.decisions if d.text],
            todos=[t.text for t in insights.todos if t.text],
            facts=[f.text for f in insights.facts if f.text],
            message_text=text
        )
        await self.db.save_insight(record)
        
        # 4. Jira Sync (if enabled and todos exist)
        if insights.todos and settings.jira_project_key:
            created_keys = []
            for todo in insights.todos:
                if not todo.text: continue
                # Basic idempotency check could go here or in adapter
                key = await self.jira.create_ticket(
                    project_key=settings.jira_project_key,
                    summary=todo.text[:254],
                    description=f"{todo.text}\n\nSource: Slack channel {channel_id}",
                    labels=["ai-shadow", "from-slack"]
                )
                if key:
                    created_keys.append(key)
            
            # 5. Notify Slack thread
            if created_keys:
                links = ", ".join(created_keys)
                await self.slack.post_thread_reply(channel_id, ts, f"Created Jira issues: {links}")
        
        # 6. Post Summary to Target Channel (if configured)
        if settings.report_post_channel_id and (insights.decisions or insights.todos or insights.facts):
             # Simple format
            lines = ["🤖 *AI Insights Extracted:*"]
            if insights.decisions:
                lines.append(f"⚡ *Decisions*: " + ", ".join([d.text for d in insights.decisions if d.text]))
            if insights.todos:
                lines.append(f"📋 *Todos*: " + ", ".join([t.text for t in insights.todos if t.text]))
            if insights.facts:
                lines.append(f"💡 *Facts*: " + ", ".join([f.text for f in insights.facts if f.text]))
            
            await self.slack.post_message(settings.report_post_channel_id, "\n".join(lines))
