from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class AuditModel(BaseModel):
    """Base model that includes audit timestamps."""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
