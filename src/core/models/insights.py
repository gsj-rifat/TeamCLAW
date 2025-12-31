from uuid import UUID, uuid4
from typing import List, Optional
from pydantic import Field, BaseModel

from src.core.models.base import AuditModel

# --- Base Insight ---
class BaseInsight(AuditModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: Optional[UUID] = None  # The SaaS user ID, if known
    slack_user_id: Optional[str] = None # The original Slack user ID
    text: str
    reason: Optional[str] = None
    channel_id: Optional[str] = None
    message_ts: Optional[str] = None

# --- Domain Models ---
class Decision(BaseInsight):
    pass

class Todo(BaseInsight):
    pass

class Fact(BaseInsight):
    pass

# --- Extraction DTOs (Data Transfer Objects) ---
# These are used for the raw output from the LLM, before we attach tenant context.
class ExtractedItem(BaseModel):
    text: str
    reason: Optional[str] = None

class ExtractedInsights(BaseModel):
    decisions: List[ExtractedItem] = Field(default_factory=list)
    todos: List[ExtractedItem] = Field(default_factory=list)
    facts: List[ExtractedItem] = Field(default_factory=list)

# --- Legacy/Storage Record (Optional, kept for backward compat if needed, but updated) ---
class InsightRecord(AuditModel):
    id: Optional[int] = None # Auto-incrementing int for SQLite compatibility
    # Timestamps inherited from AuditModel (created_at, updated_at)
    date: str
    channel_id: Optional[str]
    slack_user_id: Optional[str]
    
    # We might store the raw JSON blobs here, or move to normalized tables for Decisions/Todos/Facts.
    # For now, keeping the structure compatible with the SQLiteAdapter but using the new base.
    decisions: List[str]
    todos: List[str]
    facts: List[str]
    message_text: str
