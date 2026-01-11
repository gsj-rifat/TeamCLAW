"""
Slack-First Tenant Identity & Auto-Provisioning

This module handles automatic tenant creation/lookup based on Slack Team ID.
Every Slack workspace gets its own isolated data bucket automatically.
"""
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.db_schema import TenantModel


async def get_or_create_tenant_by_slack_id(
    session_maker: async_sessionmaker,
    slack_team_id: str,
    team_name: str = "Unknown Workspace"
) -> UUID:
    """
    Get or create a tenant by Slack Team ID.
    
    Args:
        session_maker: SQLAlchemy async session maker
        slack_team_id: The Slack workspace/team ID (e.g., "T09AH5EBDS8")
        team_name: Human-readable name for the workspace (used when creating)
    
    Returns:
        UUID of the tenant (existing or newly created)
    """
    async with session_maker() as session:
        # Try to find existing tenant by slack_team_id
        result = await session.execute(
            select(TenantModel).where(TenantModel.slack_team_id == slack_team_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing.id
        
        # Create new tenant for this Slack workspace
        new_tenant = TenantModel(
            id=uuid4(),
            name=team_name,
            domain=f"{slack_team_id}.slack.local",  # Synthetic domain
            slack_team_id=slack_team_id
        )
        session.add(new_tenant)
        await session.commit()
        
        print(f"INFO: Created new tenant for Slack workspace {slack_team_id}")
        return new_tenant.id
