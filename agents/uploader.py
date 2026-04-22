"""
Agent 4 – Uploader
Uploads each video to all active accounts matching its language via Zernio.
TikTok, Instagram and YouTube per language = 3 uploads per video.
"""
import json
import logging
import os
from typing import List, Optional

import requests

from config import settings
from supabase_client import get_client, log

logger = logging.getLogger(__name__)

ZERNIO_BASE = "https://zernio.com/api/v1"


def _zernio_headers() -> dict:
    return {"Authorization": f"Bearer {settings.zernio_api_key}"}


def _presign_upload(filename: str) -> dict:
    """Get a presigned URL to upload the video file."""
    resp = requests.post(
        f"{ZERNIO_BASE}/media/presign",
        headers=_zernio_headers(),
        json={"fileName": filename, "fileType": "video/mp4"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _upload_to_presigned(presigned_url: str, video_path: str):
    """PUT the video file to the presigned URL."""
    with open(video_path, "rb") as f:
        resp = requests.put(
            presigned_url,
            data=f,
            headers={"Content-Type": "video/mp4"},
            timeout=300,
        )
    resp.raise_for_status()


def _post_to_accounts(public_url: str, account_ids: List[str], caption: str, hashtags: List[str]) -> dict:
    """Create a post across multiple accounts via Zernio."""
    text = f"{caption}\n\n{' '.join(hashtags)}"
    resp = requests.post(
        f"{ZERNIO_BASE}/post",
        headers={**_zernio_headers(), "Content-Type": "application/json"},
        json={
            "text": text,
            "socialAccountIds": account_ids,
            "mediaItems": [{"url": public_url, "type": "video"}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _upload_video(video_path: str, account_ids: List[str], caption: str, hashtags: List[str]) -> dict:
    """Full Zernio upload flow: presign → upload → post."""
    filename = os.path.basename(video_path)

    presign_data = _presign_upload(filename)
    presigned_url = presign_data.get("url") or presign_data.get("presignedUrl")
    public_url    = presign_data.get("publicUrl") or presign_data.get("fileUrl")

    _upload_to_presigned(presigned_url, video_path)
    post_data = _post_to_accounts(public_url, account_ids, caption, hashtags)

    return {
        "zernio_post_id": post_data.get("id"),
        "post_url":       post_data.get("url") or "",
    }


def run(run_id: str, video_ids: Optional[List[int]] = None) -> int:
    sb = get_client()
    log("uploader", run_id, "info", "Uploader gestartet")

    if video_ids:
        result = sb.table("videos").select("*").in_("id", video_ids).eq("status", "READY").execute()
    else:
        result = sb.table("videos").select("*").eq("status", "READY").execute()

    videos = result.data
    if not videos:
        log("uploader", run_id, "warning", "Keine READY Videos gefunden")
        return 0

    total_uploads = 0
    for video in videos:
        vid_id = video["id"]
        lang   = video["language"]
        path   = video["video_path"]

        if not path or not os.path.exists(path):
            log("uploader", run_id, "error", f"Video #{vid_id} Datei nicht gefunden: {path}")
            continue

        # Get active accounts for this language
        accounts_result = sb.table("accounts") \
            .select("*") \
            .eq("language", lang) \
            .eq("is_active", True) \
            .execute()
        accounts = accounts_result.data

        if not accounts:
            log("uploader", run_id, "warning",
                f"Keine aktiven Accounts für Sprache {lang} — überspringe Video #{vid_id}")
            sb.table("videos").update({"status": "SKIPPED"}).eq("id", vid_id).execute()
            continue

        # Get topic for caption
        topic_result = sb.table("topics").select("title,hook").eq("id", video["topic_id"]).execute()
        topic = topic_result.data[0] if topic_result.data else {}
        caption  = topic.get("hook") or topic.get("title", "")
        hashtags = ["#Psychology", "#MindFacts", "#LearnOnTikTok", f"#{lang}"]

        # Upload to all accounts of this language
        account_ids = [a["zernio_account_id"] for a in accounts]
        log("uploader", run_id, "info",
            f"Video #{vid_id} ({lang}) → {len(account_ids)} Accounts ({', '.join(a['platform'] for a in accounts)})")

        try:
            upload_result = _upload_video(path, account_ids, caption, hashtags)

            # Record each upload
            for acc in accounts:
                sb.table("uploads").insert({
                    "video_id":       vid_id,
                    "account_id":     acc["id"],
                    "zernio_post_id": upload_result.get("zernio_post_id"),
                    "post_url":       upload_result.get("post_url"),
                    "status":         "PUBLISHED",
                    "uploaded_at":    "now()",
                }).execute()
                total_uploads += 1

            sb.table("videos").update({"status": "UPLOADED"}).eq("id", vid_id).execute()
            log("uploader", run_id, "info",
                f"  ✓ Video #{vid_id} ({lang}) hochgeladen auf {len(account_ids)} Accounts")

        except Exception as e:
            log("uploader", run_id, "error",
                f"  Upload fehlgeschlagen für Video #{vid_id} ({lang}): {e}")
            sb.table("videos").update({"status": "FAILED"}).eq("id", vid_id).execute()
            for acc in accounts:
                sb.table("uploads").insert({
                    "video_id":      vid_id,
                    "account_id":    acc["id"],
                    "status":        "FAILED",
                    "error_message": str(e),
                }).execute()

    log("uploader", run_id, "info", f"Uploader fertig — {total_uploads} Uploads gesamt")
    return total_uploads
