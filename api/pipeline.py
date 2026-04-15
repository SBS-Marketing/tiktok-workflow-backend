import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException

from orchestrator import get_state, run_pipeline
from supabase_client import get_client

router = APIRouter()


@router.post("/run")
async def start_pipeline():
    if get_state()["is_running"]:
        raise HTTPException(status_code=409, detail="Pipeline läuft bereits")
    asyncio.create_task(run_pipeline())
    return {"status": "started", "message": "Pipeline gestartet"}


@router.get("/status")
async def pipeline_status():
    return get_state()


@router.get("/history")
def pipeline_history(limit: int = 20):
    sb = get_client()
    result = sb.table("content_pieces").select("*").order("created_at", desc=True).limit(limit).execute()
    return result.data


@router.get("/logs")
def pipeline_logs(run_id: Optional[str] = None, agent: Optional[str] = None, limit: int = 100):
    sb = get_client()
    q = sb.table("agent_logs").select("*").order("timestamp", desc=True)
    if run_id:
        q = q.eq("run_id", run_id)
    if agent:
        q = q.eq("agent_name", agent)
    return q.limit(limit).execute().data
