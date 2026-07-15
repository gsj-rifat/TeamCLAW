from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    slack_bot_token: Optional[str] = None
    slack_signing_secret: Optional[str] = None
    target_channel_id: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("TARGET_CHANNEL_ID", "SLACK_CHANNEL_ID"),
    )
    report_post_channel_id: Optional[str] = None

    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    jira_project_key: Optional[str] = None

    default_tenant_id: str = "00000000-0000-0000-0000-000000000000"
    dashboard_tenant_id: Optional[str] = None

    postgres_user: Optional[str] = "postgres"
    postgres_password: Optional[str] = "postgres"
    postgres_db: Optional[str] = "webhook_server"
    postgres_host: Optional[str] = "localhost"
    postgres_port: Optional[str] = "5432"

    external_database_url: Optional[str] = Field(None, alias="DATABASE_URL")

    noise_filter_enabled: bool = True
    noise_min_chars: int = 12
    noise_llm_threshold: float = 0.55

    @property
    def database_url(self) -> str:
        if self.external_database_url:
            url = self.external_database_url
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+asyncpg://", 1)
            if url.startswith("postgresql://") and "+asyncpg" not in url:
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url

        if self.postgres_user and self.postgres_host:
            return (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )

        raise ValueError(
            "DATABASE_URL or POSTGRES_* variables are required. "
            "PostgreSQL is mandatory for TeamCLAW."
        )

    @property
    def effective_dashboard_tenant_id(self) -> str:
        return self.dashboard_tenant_id or self.default_tenant_id

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
