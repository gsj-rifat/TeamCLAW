import os

# Minimal env so Settings() loads in CI without a real .env file.
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/teamclaw_test",
)
