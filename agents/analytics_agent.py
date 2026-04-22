"""
Agent 5 – Analytics
Fetches performance data from Zernio for all published uploads.
"""
import logging
from typing import Optional
import requests
from config import settings
from supabase_client import get_client, log

logger = logging.getLogger(__name__)
ZERNIO_BASE = "https://zernio.com/api/v1"


def _fetch_post_analytics(zernio_post_id: str) -> Optional[dict]:
    try:
        resp = requests.get(
            f"{ZERNIO_BASE}/posts/{zernio_post_id}",
            headers={"Authorization": f"Bearer {settings.zernio_api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        stats = data.get("analytics") or data.get("stats") or {}
        return {
            "views":    stats.get("views", 0),
            "likes":    stats.get("likes", 0),
            "comments": stats.get("comments", 0),
            "shares":   stats.get("shares", 0),
        }
    except Exception as e:
        logger.warning("Analytics fetch failed for post %s: %s", zernio_post_id, e)
        return None


def run(run_id: str) -> int:
    sb = get_client()
    log("analytics_agent", run_id, "info", "Analytics Agent gestartet")
    uploads = sb.table("uploads").select("*").eq("status", "PUBLISHED").execute().data
    if not uploads:
        log("analytics_agent", run_id, "info", "Keine PUBLISHED Uploads gefunden")
        return 0
    fetched = 0
    for upload in uploads:
        if not upload.get("zernio_post_id"):
            continue
        stats = _fetch_post_analytics(upload["zernio_post_id"])
        if stats:
            sb.table("analytics").insert({"upload_id": upload["id"], **stats}).execute()
            fetched += 1
    log("analytics_agent", run_id, "info", f"Analytics fertig — {fetched} Uploads ausgewertet")
    return fetched
