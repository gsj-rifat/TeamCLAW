from pydantic import BaseModel, Field
from typing import List, Optional

class InsightItem(BaseModel):
    text: str
    reason: Optional[str] = None

class ExtractedInsights(BaseModel):
    decisions: List[InsightItem] = Field(default_factory=list)
    todos: List[InsightItem] = Field(default_factory=list)
    facts: List[InsightItem] = Field(default_factory=list)

class InsightRecord(BaseModel):
    id: Optional[int] = None
    created_at: int
    date: str
    channel_id: Optional[str]
    user_id: Optional[str]
    decisions: List[str]
    todos: List[str]
    facts: List[str]
    message_text: str
