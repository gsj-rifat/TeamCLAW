from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    groq_api_key: str
    groq_model: str = "llama3-70b-8192"

    slack_bot_token: Optional[str] = None
    slack_signing_secret: Optional[str] = None
    target_channel_id: Optional[str] = None
    report_post_channel_id: Optional[str] = None

    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    jira_project_key: Optional[str] = None
    
    # Defaults
    default_tenant_id: str = "00000000-0000-0000-0000-000000000000" # Null UUID for singular/MVP deployment

    # Database (Postgres) components
    postgres_user: Optional[str] = "postgres"
    postgres_password: Optional[str] = "postgres"
    postgres_db: Optional[str] = "webhook_server"
    postgres_host: Optional[str] = "localhost"
    postgres_port: Optional[str] = "5432"

    # Direct URL Override (e.g. Supabase) - Aliased to standard DATABASE_URL env var
    external_database_url: Optional[str] = Field(None, alias="DATABASE_URL")

    # Legacy
    insights_db_path: str = "insights.db"
    
    # Noise Filter settings
    noise_filter_enabled: bool = True
    noise_min_chars: int = 12
    noise_llm_threshold: float = 0.55

    @property
    def database_url(self) -> str:
        # Prioritize external/direct URL if provided (e.g. from Supabase)
        if self.external_database_url:
            # Fix for SQLAlchemy AsyncPG compatibility if protocol is just 'postgres://'
            if self.external_database_url.startswith("postgres://"):
                return self.external_database_url.replace("postgres://", "postgresql+asyncpg://", 1)
            if self.external_database_url.startswith("postgresql://") and "+asyncpg" not in self.external_database_url:
                 return self.external_database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self.external_database_url

        # Fallback to constructed URL
        if self.postgres_user and self.postgres_host:
             return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        
        # Fallback to SQLite
        return "sqlite+aiosqlite:///insights.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
