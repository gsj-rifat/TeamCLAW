from datetime import datetime
from typing import Optional
from uuid import UUID
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

    async def process_message(self, text: str, channel_id: str, user_id: str, ts: str, tenant_id: Optional[UUID] = None) -> None:
        # Use provided tenant_id or fall back to default
        effective_tenant_id = tenant_id if tenant_id else UUID(settings.default_tenant_id)
        
        # 1. Noise Filter
        meaningful, reason = await self.extractor.is_meaningful(text)
        if not meaningful:
            print(f"Skipping message: {reason}")
            return

        # 2. Extract Insights
        insights = await self.extractor.extract(text)
        
        # 3. Get Proof of Insight (permalink to original message)
        source_url = ""
        if hasattr(self.slack, 'get_permalink'):
            source_url = await self.slack.get_permalink(channel_id, ts)
        
        # 4. Save to DB with enriched todo data
        now = datetime.utcnow()  # Naive UTC datetime for TIMESTAMP WITHOUT TIME ZONE
        
        # Build todos list with assignee and due_date as structured objects
        todos_data = []
        for t in insights.todos:
            if t.text:
                todos_data.append({
                    "text": t.text,
                    "assignee": t.assignee,
                    "due_date": t.due_date
                })
        
        record = InsightRecord(
            tenant_id=effective_tenant_id,
            created_at=now,
            date=now.strftime("%Y-%m-%d"),
            channel_id=channel_id,
            slack_user_id=user_id,
            source_url=source_url,  # Proof of Insight
            decisions=[d.text for d in insights.decisions if d.text],
            todos=[t["text"] for t in todos_data],  # Text-only for backward compat
            facts=[f.text for f in insights.facts if f.text],
            message_text=text
        )
        await self.db.save_insight(record, tenant_id=effective_tenant_id)
        
        # 5. Jira Sync (if enabled and todos exist)
        if insights.todos and settings.jira_project_key:
            created_keys = []
            for todo in insights.todos:
                if not todo.text: continue
                # Include assignee and due_date in Jira description
                description_parts = [todo.text]
                if todo.assignee:
                    description_parts.append(f"Assignee: {todo.assignee}")
                if todo.due_date:
                    description_parts.append(f"Due: {todo.due_date}")
                if source_url:
                    description_parts.append(f"Source: {source_url}")
                else:
                    description_parts.append(f"Source: Slack channel {channel_id}")
                
                key = await self.jira.create_ticket(
                    project_key=settings.jira_project_key,
                    summary=todo.text[:254],
                    description="\n\n".join(description_parts),
                    labels=["ai-shadow", "from-slack"]
                )
                if key:
                    created_keys.append(key)
            
            # 6. Notify Slack thread
            if created_keys:
                links = ", ".join(created_keys)
                await self.slack.post_thread_reply(channel_id, ts, f"Created Jira issues: {links}")
        
        # 7. Post Summary to Target Channel (if configured)
        if settings.target_channel_id and (insights.decisions or insights.todos or insights.facts):
            lines = ["🤖 *AI Insights Extracted:*"]
            if insights.decisions:
                lines.append(f"⚡ *Decisions*: " + ", ".join([d.text for d in insights.decisions if d.text]))
            if insights.todos:
                todo_lines = []
                for t in insights.todos:
                    if t.text:
                        parts = [t.text]
                        if t.assignee:
                            parts.append(f"→ {t.assignee}")
                        if t.due_date:
                            parts.append(f"(by {t.due_date})")
                        todo_lines.append(" ".join(parts))
                lines.append(f"📋 *Todos*: " + ", ".join(todo_lines))
            if insights.facts:
                lines.append(f"💡 *Facts*: " + ", ".join([f.text for f in insights.facts if f.text]))
            if source_url:
                lines.append(f"📎 <{source_url}|View original message>")
            
            await self.slack.post_message(settings.target_channel_id, "\n".join(lines))

