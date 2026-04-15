import asyncio
import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from supabase_client import get_config

logging.basicConfig(level=logging.INFO)
scheduler = AsyncIOScheduler()


async def run_scheduled_pipeline():
    from orchestrator import run_pipeline
    await run_pipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(run_scheduled_pipeline, "cron", hour=9, minute=0,
                      id="daily_pipeline", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="TikTok Workflow Agent Runner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Allow all origins on Railway if CORS_ORIGINS=* is set
# (Lovable URL is *.lovable.app — set CORS_ORIGINS=* in Railway env vars)

os.makedirs(settings.media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

from api.pipeline import router as pipeline_router
app.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])


@app.get("/health")
async def health():
    return {"status": "ok", "supabase_url": settings.supabase_url}
