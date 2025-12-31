from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Table
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class TenantModel(Base):
    __tablename__ = "tenants"
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("UserModel", back_populates="tenant")
    insights = relationship("InsightModel", back_populates="tenant")

class UserModel(Base):
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String, default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("TenantModel", back_populates="users")

class InsightModel(Base):
    """
    SQL storage for the 'InsightRecord'.
    Stores raw extracted lists (decisions, etc) as JSONB for flexibility,
    or could be normalized further. For this MVP, mapping InsightRecord directly.
    """
    __tablename__ = "insights"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    date: Mapped[str] = mapped_column(String, index=True)
    channel_id: Mapped[str] = mapped_column(String, nullable=True)
    user_id: Mapped[str] = mapped_column(String, nullable=True) # Slack user ID
    
    # Storing lists as JSONB
    decisions: Mapped[dict] = mapped_column(JSONB, default=list)
    todos: Mapped[dict] = mapped_column(JSONB, default=list)
    facts: Mapped[dict] = mapped_column(JSONB, default=list)
    
    message_text: Mapped[str] = mapped_column(Text)

    tenant = relationship("TenantModel", back_populates="insights")

async def init_db(engine: AsyncEngine):
    """
    Initializes the database by creating all tables defined in this schema.
    This is safe to run on startup (idempotent).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
