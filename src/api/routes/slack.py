from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from src.core.logic.identity import get_or_create_tenant_by_slack_id
from src.core.logic.slack_security import verify_slack_signature
from src.infrastructure.config import settings
from src.infrastructure.container import container
from src.infrastructure.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


async def verify_slack_request(request: Request) -> None:
    if not settings.slack_signing_secret:
        return

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    body_bytes = await request.body()
    req_body = body_bytes.decode("utf-8")

    if not verify_slack_signature(
        settings.slack_signing_secret, timestamp, req_body, signature
    ):
        raise HTTPException(status_code=403, detail="Invalid signature")


@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    try:
        await verify_slack_request(request)
    except HTTPException:
        logger.warning("Slack signature verification failed")
        raise

    data = await request.json()

    if "challenge" in data:
        return JSONResponse(content={"challenge": data["challenge"]})

    slack_team_id = data.get("team_id", "")
    tenant_id = None
    if slack_team_id:
        tenant_id = await get_or_create_tenant_by_slack_id(
            container.db.async_session,
            slack_team_id,
            team_name=f"Slack Workspace {slack_team_id}",
        )
        logger.info("Resolved tenant_id=%s for team_id=%s", tenant_id, slack_team_id)

    if "event" in data:
        event = data["event"]
        event_type = event.get("type")
        bot_id = event.get("bot_id")
        subtype = event.get("subtype")

        is_user_message = event_type == "message" and not bot_id and not subtype
        is_app_mention = event_type == "app_mention" and not bot_id

        if is_user_message or is_app_mention:
            background_tasks.add_task(
                container.workflow.process_message,
                event.get("text", ""),
                event.get("channel", ""),
                event.get("user", ""),
                event.get("ts", ""),
                tenant_id,
                is_app_mention,
            )
        else:
            logger.debug(
                "Skipping Slack event type=%s bot_id=%s subtype=%s",
                event_type,
                bot_id,
                subtype,
            )

    return JSONResponse(content={"status": "processed"})
