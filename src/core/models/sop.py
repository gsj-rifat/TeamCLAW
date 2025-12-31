from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class Sop(BaseModel):
    id: Optional[int] = None
    title: str
    topic: str
    content: str
    channel_id: Optional[str] = None
    created_by: Optional[str] = None
    status: str = "active"
    tags: Optional[List[str]] = None
    created_at: int
    version: str = "v1"

class Sopreadiness(BaseModel):
    is_complete: bool
    missing_info: List[str] = Field(default_factory=list)
    clarification_prompt: Optional[str] = None
