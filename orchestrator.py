"""
Orchestrator – chains all 4 agents into a single pipeline run.
Status updates go directly to Supabase → Lovable picks them up via Realtime.
"""
import asyncio
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)

_pipeline_lock = asyncio.Lock()
_pipeline_state: dict = {"is_running": False, "run_id": None, "current_stage": None}


def get_state() -> dict:
    return dict(_pipeline_state)


async def run_pipeline():
    if _pipeline_lock.locked():
        logger.warning("Pipeline läuft bereits, überspringe")
        return

    async with _pipeline_lock:
        run_id = str(uuid4())
        _pipeline_state.update({"is_running": True, "run_id": run_id, "current_stage": None})
        logger.info("[orchestrator] Pipeline gestartet, run_id=%s", run_id)

        try:
            # Stage 1 – Trend Scout
            _pipeline_state["current_stage"] = "trend_scout"
            from agents import trend_scout
            created_ids = await asyncio.to_thread(trend_scout.run, run_id)

            # Stage 2 – Script Writer (Top-Piece)
            _pipeline_state["current_stage"] = "script_writer"
            from agents import script_writer
            content_id = created_ids[0] if created_ids else None
            script_id = await asyncio.to_thread(script_writer.run, run_id, content_id)

            # Stage 3 – Video Producer
            _pipeline_state["current_stage"] = "video_producer"
            from agents import video_producer
            video_id = await asyncio.to_thread(
                video_producer.run, run_id, script_id if script_id > 0 else None
            )

            # Stage 4 – Analytics
            _pipeline_state["current_stage"] = "analytics_agent"
            from agents import analytics_agent
            await asyncio.to_thread(analytics_agent.run, run_id)

            logger.info("[orchestrator] Pipeline erfolgreich abgeschlossen, run_id=%s", run_id)

        except Exception as e:
            stage = _pipeline_state.get("current_stage", "unknown")
            logger.error("[orchestrator] Pipeline FEHLER bei %s: %s", stage, e)
            try:
                from supabase_client import log as sb_log
                sb_log("orchestrator", run_id, "error", f"Pipeline FEHLER bei {stage}: {e}")
            except Exception:
                pass
        finally:
            _pipeline_state.update({"is_running": False, "run_id": None, "current_stage": None})
