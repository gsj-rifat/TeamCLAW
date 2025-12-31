from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from src.infrastructure.container import container

router = APIRouter()

@router.get("/daily")
async def daily_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    channel_id: Optional[str] = None
):
    if date:
        try:
            report_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        report_date = datetime.now()

    report = await container.reporter.generate_daily_report(report_date, channel_id)
    return {"report": report}

@router.get("/weekly")
async def weekly_report(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    channel_id: Optional[str] = None
):
    if start_date:
        try:
            date = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        date = datetime.now()

    report = await container.reporter.generate_weekly_report(date, channel_id)
    return {"report": report}
