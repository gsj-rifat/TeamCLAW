"""
Slack-First Tenant Identity & Auto-Provisioning

Resolves or creates a tenant for each Slack workspace.
The first workspace links to the default tenant so the dashboard stays in sync.
"""
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.config import settings
from src.infrastructure.db_schema import TenantModel
from src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


async def get_or_create_tenant_by_slack_id(
    session_maker: async_sessionmaker,
    slack_team_id: str,
    team_name: str = "Unknown Workspace",
) -> UUID:
    default_tenant_id = UUID(settings.default_tenant_id)

    async with session_maker() as session:
        result = await session.execute(
            select(TenantModel).where(TenantModel.slack_team_id == slack_team_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing.id

        result = await session.execute(
            select(TenantModel).where(TenantModel.id == default_tenant_id)
        )
        default_tenant = result.scalar_one_or_none()
        if default_tenant and not default_tenant.slack_team_id:
            default_tenant.slack_team_id = slack_team_id
            default_tenant.name = team_name
            await session.commit()
            logger.info(
                "Linked Slack workspace %s to default tenant %s",
                slack_team_id,
                default_tenant_id,
            )
            return default_tenant.id

        new_tenant = TenantModel(
            id=uuid4(),
            name=team_name,
            domain=f"{slack_team_id}.slack.local",
            slack_team_id=slack_team_id,
        )
        session.add(new_tenant)
        await session.commit()
        logger.info("Created tenant %s for Slack workspace %s", new_tenant.id, slack_team_id)
        return new_tenant.id
