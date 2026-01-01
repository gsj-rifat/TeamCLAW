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
    print("DEBUG: Received /slack/events request")
    
    # 1. Verify Request
    try:
        await verify_slack_request(request)
        print("DEBUG: Signature verification successful")
    except HTTPException as e:
        print(f"DEBUG: Signature verification failed: {e.detail}")
        raise e
    except Exception as e:
        print(f"DEBUG: Unexpected error in signature verification: {e}")
        raise e
    
    data = await request.json()
    print(f"DEBUG: Request payload: {data}")
    
    if "challenge" in data:
        print("DEBUG: Responding to URL challenge")
        return JSONResponse(content={"challenge": data["challenge"]})
        
    if "event" in data:
        event = data["event"]
        event_type = event.get("type")
        bot_id = event.get("bot_id")
        print(f"DEBUG: Event type: {event_type}, Bot ID: {bot_id}")
        
        if event_type == "message" and not bot_id:
            text = event.get("text", "")
            user = event.get("user", "")
            channel = event.get("channel", "")
            ts = event.get("ts", "")
            
            print(f"DEBUG: Processing valid user message: {text[:20]}... from User {user} in Channel {channel}")
            
            # Use BackgroundTasks for async processing to return 200 OK fast to Slack
            background_tasks.add_task(
                container.workflow.process_message, 
                text, channel, user, ts
            )
        else:
            print("DEBUG: Skipping event (type mismatch or bot message)")
            
    return JSONResponse(content={"status": "processed"})
