import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.infrastructure.container import container
from src.core.models.sop import Sop

router = APIRouter()

class SopRequest(BaseModel):
    topic: str
    context: List[str] = []

@router.post("/generate")
async def generate_sop(req: SopRequest):
    readiness = await container.sop_gen.check_readiness(req.topic, req.context)
    if not readiness.is_complete:
        return {
            "status": "incomplete",
            "missing": readiness.missing_info
        }
        
    sop_text = await container.sop_gen.generate_sop(req.topic, req.context)
    
    new_sop = Sop(
        title=f"SOP: {req.topic}",
        topic=req.topic,
        content=sop_text,
        created_at=int(time.time())
    )
    
    sop_id = await container.db.save_sop(new_sop)
    
    return {
        "status": "created",
        "id": sop_id,
        "content": sop_text
    }
