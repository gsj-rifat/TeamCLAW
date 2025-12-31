import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from src.infrastructure.config import settings
from src.infrastructure.container import container

router = APIRouter()

async def verify_slack_request(request: Request):
    if not settings.slack_signing_secret:
        return True
        
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    
    if not timestamp or not signature:
        raise HTTPException(status_code=403, detail="Invalid signature headers")
        
    body_bytes = await request.body()
    req_body = body_bytes.decode("utf-8")
    
    sig_basestring = f"v0:{timestamp}:{req_body}"
    expected_signature = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    await verify_slack_request(request)
    
    data = await request.json()
    
    if "challenge" in data:
        return JSONResponse(content={"challenge": data["challenge"]})
        
    if "event" in data:
        event = data["event"]
        if event.get("type") == "message" and not event.get("bot_id"):
            text = event.get("text", "")
            user = event.get("user", "")
            channel = event.get("channel", "")
            ts = event.get("ts", "")
            
            # Use BackgroundTasks for async processing to return 200 OK fast to Slack
            background_tasks.add_task(
                container.workflow.process_message, 
                text, channel, user, ts
            )
            
    return JSONResponse(content={"status": "processed"})
