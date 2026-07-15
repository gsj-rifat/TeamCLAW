"""
Dashboard API Router
Provides endpoints expected by the dashboard frontend.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Query, Header

from src.infrastructure.container import container
from src.infrastructure.config import settings

router = APIRouter()

def get_tenant_id() -> UUID:
    return UUID(settings.effective_dashboard_tenant_id)

@router.get("/reports")
async def get_reports(
    granularity: str = Query("daily"),
    start: str = Query(...),
    end: str = Query(...),
    channel_id: Optional[str] = None,
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token")
):
    """Get reports for dashboard overview."""
    # Parse dates
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return {"status": "error", "error": "Invalid date format"}
    
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) + 86400  # Include end day
    
    tenant_id = get_tenant_id()
    insights = await container.db.fetch_insights(start_ts, end_ts, channel_id, tenant_id)
    
    # Aggregate counts
    total_decisions = sum(len(i.decisions) for i in insights)
    total_todos = sum(len(i.todos) for i in insights)
    total_facts = sum(len(i.facts) for i in insights)
    
    items = [{
        "label": f"{granularity.capitalize()} Report",
        "period": f"{start} to {end}",
        "channel_filter": channel_id or "",
        "counts": {
            "decisions": total_decisions,
            "todos": total_todos,
            "facts": total_facts
        },
        "report_text": f"Found {len(insights)} insights with {total_decisions} decisions, {total_todos} todos, {total_facts} facts."
    }]
    
    return {"status": "ok", "items": items}

@router.get("/sops")
async def get_sops(
    q: Optional[str] = None,
    status: Optional[str] = None,
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token")
):
    """Get SOPs for dashboard."""
    sops = await container.db.fetch_sops(limit=100, status=status)
    items = [
        {
            "id": s.id,
            "topic": s.topic,
            "tags": ",".join(s.tags) if s.tags else "",
            "status": s.status,
            "created_at": s.created_at.isoformat() if hasattr(s.created_at, 'isoformat') else str(s.created_at),
            "sop_text": s.sop_text
        }
        for s in sops
    ]
    return {"status": "ok", "items": items}

@router.get("/summaries")
async def get_summaries(
    q: Optional[str] = None,
    status: Optional[str] = None,
    channel_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token")
):
    """Get summaries for dashboard - stub for now."""
    # TODO: Implement summaries storage and retrieval
    return {"status": "ok", "items": []}

@router.get("/activities")
async def get_activities(
    start: Optional[str] = None,
    end: Optional[str] = None,
    channel_id: Optional[str] = None,
    status: Optional[str] = None,
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token")
):
    """Get recent activities for dashboard."""
    # Parse dates if provided
    start_ts = 0
    end_ts = int(datetime.now().timestamp()) + 86400
    
    if start:
        try:
            start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp())
        except ValueError:
            pass
    if end:
        try:
            end_ts = int(datetime.strptime(end, "%Y-%m-%d").timestamp()) + 86400
        except ValueError:
            pass
    
    tenant_id = get_tenant_id()
    insights = await container.db.fetch_insights(start_ts, end_ts, channel_id, tenant_id)
    
    items = [
        {
            "id": i.id,
            "type": "insight",
            "title": f"Insight from {i.channel_id or 'unknown'}",
            "description": i.message_text[:100] + "..." if len(i.message_text) > 100 else i.message_text,
            "channel_id": i.channel_id,
            "created_at": i.created_at.isoformat() if hasattr(i.created_at, 'isoformat') else str(i.created_at),
            "meta": {
                "counts": {
                    "decisions": len(i.decisions),
                    "todos": len(i.todos),
                    "facts": len(i.facts)
                }
            }
        }
        for i in insights[:50]  # Limit to 50 recent
    ]
    
    return {"status": "ok", "items": items}

@router.get("/search")
async def search_insights(
    q: Optional[str] = None,
    channel_id: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token")
):
    """Search insights for global search."""
    start_ts = 0
    end_ts = int(datetime.now().timestamp()) + 86400
    
    if start:
        try:
            start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp())
        except ValueError:
            pass
    if end:
        try:
            end_ts = int(datetime.strptime(end, "%Y-%m-%d").timestamp()) + 86400
        except ValueError:
            pass
    
    tenant_id = get_tenant_id()
    insights = await container.db.fetch_insights(start_ts, end_ts, channel_id, tenant_id)
    
    # Filter by query if provided
    if q:
        q_lower = q.lower()
        insights = [i for i in insights if q_lower in i.message_text.lower()]
    
    items = [
        {
            "id": i.id,
            "type": "insight",
            "title": f"Insight {i.id}",
            "text": i.message_text,
            "channel_id": i.channel_id,
            "date": i.date,
            "created_at": i.created_at.isoformat() if hasattr(i.created_at, 'isoformat') else str(i.created_at)
        }
        for i in insights[:50]
    ]
    
    return {"status": "ok", "items": items}
