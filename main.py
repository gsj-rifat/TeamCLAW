from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.infrastructure.container import container
from src.infrastructure.config import settings
from src.infrastructure.db_schema import init_db
from src.api.routes import slack, reports, sop, dashboard_api

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize resources
    await container.init_resources()
    
    # Explicitly ensure tables exist (User Request)
    # accessing engine from the adapter
    await init_db(container.db.engine)
    
    yield
    # Shutdown: Cleanup if needed (nothing for now)

app = FastAPI(
    title="AI Shadow Coach",
    description="GenAI-Native Webhook Server",
    version="2.0.0",
    lifespan=lifespan
)

from fastapi.responses import RedirectResponse

# ... (imports)

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

# Health Check
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "config": {
            "groq": bool(settings.groq_api_key),
            "slack": bool(settings.slack_bot_token),
            "jira": bool(settings.jira_base_url)
        }
    }

# Mount Routes
app.include_router(slack.router, prefix="/slack", tags=["Slack"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(sop.router, prefix="/sop", tags=["SOP"])
app.include_router(dashboard_api.router, tags=["Dashboard API"])  # Dashboard API at root level

# Mount Static Dashboard
app.mount("/dashboard", StaticFiles(directory="dashboard_static", html=True), name="dashboard")