from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, and_

from src.core.interfaces.db import DatabasePort
from src.core.models.insights import InsightRecord
from src.core.models.sop import Sop
from src.infrastructure.db_schema import Base, InsightModel, TenantModel

class PostgresAdapter(DatabasePort):
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_db(self):
        async with self.engine.begin() as conn:
            # In production, use Alembic. For MVP, create tables here.
            await conn.run_sync(Base.metadata.create_all)

    # --- Insight Operations with Multi-Tenancy ---

    async def save_insight(self, insight: InsightRecord, tenant_id: UUID) -> int:
        """
        Saves an insight record linked to a specific tenant.
        Function signature extended to accept tenant_id for enforced isolation.
        """
        async with self.async_session() as session:
            db_insight = InsightModel(
                tenant_id=tenant_id,
                created_at=datetime.fromtimestamp(insight.created_at),
                date=insight.date,
                channel_id=insight.channel_id,
                user_id=insight.user_id,
                decisions=insight.decisions,
                todos=insight.todos,
                facts=insight.facts,
                message_text=insight.message_text
            )
            session.add(db_insight)
            await session.commit()
            return db_insight.id

    async def fetch_insights(self, start_ts: int, end_ts: int, channel_id: Optional[str] = None, tenant_id: UUID = None) -> List[InsightRecord]:
        """
        Fetches insights filtering by tenant_id. 
        CRITICAL: tenant_id is mandatory for security.
        """
        if not tenant_id:
            raise ValueError("tenant_id is required for fetching insights")

        start_dt = datetime.fromtimestamp(start_ts)
        end_dt = datetime.fromtimestamp(end_ts)

        query = select(InsightModel).where(
            and_(
                InsightModel.tenant_id == tenant_id,
                InsightModel.created_at >= start_dt,
                InsightModel.created_at < end_dt
            )
        )
        if channel_id:
            query = query.where(InsightModel.channel_id == channel_id)

        async with self.async_session() as session:
            result = await session.execute(query)
            rows = result.scalars().all()
            
            return [
                InsightRecord(
                    id=row.id,
                    created_at=int(row.created_at.timestamp()),
                    date=row.date,
                    channel_id=row.channel_id,
                    user_id=row.user_id,
                    decisions=row.decisions,
                    todos=row.todos,
                    facts=row.facts,
                    message_text=row.message_text
                )
                for row in rows
            ]

    # --- SOP Operations (Stub for now, needs schema update if fully migrating) ---
    async def save_sop(self, sop: Sop) -> int:
        # Placeholder: Need to add SOPModel table in db_schema.py to support this
        return 0

    async def fetch_sops(self, limit: int = 100, status: Optional[str] = None) -> List[Sop]:
        return []
