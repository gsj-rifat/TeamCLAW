from enum import Enum
from typing import Dict, Optional
from uuid import UUID, uuid4
from pydantic import Field
from src.core.models.base import AuditModel

class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"

class IntegrationProvider(str, Enum):
    SLACK = "slack"
    JIRA = "jira"
    TEAMS = "teams"

class Tenant(AuditModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    domain: str

class User(AuditModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    email: str
    role: UserRole = UserRole.MEMBER

class Integration(AuditModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    provider: IntegrationProvider
    credentials: Dict[str, str] = Field(default_factory=dict)  # stores encrypted blobs/tokens
    is_active: bool = True
