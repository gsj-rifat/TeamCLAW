from pydantic_settings import BaseSettings, SettingsConfigDict
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

    insights_db_path: str = "insights.db"
    
    # Noise Filter settings
    noise_filter_enabled: bool = True
    noise_min_chars: int = 12
    noise_llm_threshold: float = 0.55

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
