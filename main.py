from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import dashboard_api, reports, slack, sop
from src.infrastructure.config import settings
from src.infrastructure.container import container
from src.infrastructure.db_schema import init_db
from src.infrastructure.logging_config import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await container.init_resources()
    await init_db(container.db.engine)
    yield


app = FastAPI(
    title="TeamCLAW",
    description="AI assistant that captures team decisions and todos from Slack",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "TeamCLAW",
        "config": {
            "groq": bool(settings.groq_api_key),
            "slack": bool(settings.slack_bot_token),
            "jira": bool(settings.jira_base_url),
        },
    }


app.include_router(slack.router, prefix="/slack", tags=["Slack"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(sop.router, prefix="/sop", tags=["SOP"])
app.include_router(dashboard_api.router, tags=["Dashboard API"])
app.mount("/dashboard", StaticFiles(directory="dashboard_static", html=True), name="dashboard")
