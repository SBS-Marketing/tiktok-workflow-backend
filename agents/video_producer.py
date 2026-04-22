"""
Agent 3 – Video Producer
For each video_script: downloads Pexels stock clips, generates TTS voiceover,
burns subtitles, assembles final MP4 with MoviePy.
"""
import json
import logging
import os
import tempfile
from typing import List, Optional
from uuid import uuid4

import requests
from openai import OpenAI

from config import settings
from supabase_client import get_client, log

logger = logging.getLogger(__name__)

PEXELS_API = "https://api.pexels.com/videos/search"

LANG_VOICE = {
    "DE": "nova",
    "EN": "nova",
    "ES": "nova",
    "FR": "nova",
}


# ── Pexels ────────────────────────────────────────────────────────────────────

def _search_pexels_clip(keywords: List[str], duration_hint: int) -> Optional[str]:
    """Search Pexels for a stock video clip matching keywords. Returns download URL."""
    query = " ".join(keywords[:2])
    try:
        resp = requests.get(
            PEXELS_API,
            headers={"Authorization": settings.pexels_api_key},
            params={"query": query, "per_page": 5, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if not videos:
            return None
        # Pick best matching clip by duration
        for v in videos:
            for file in v.get("video_files", []):
                if file.get("quality") in ("hd", "sd") and file.get("height", 0) >= 720:
                    return file["link"]
        return videos[0]["video_files"][0]["link"] if videos[0].get("video_files") else None
    except Exception as e:
        logger.warning("Pexels search failed for '%s': %s", query, e)
        return None


def _download_file(url: str, out_path: str):
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


# ── TTS ───────────────────────────────────────────────────────────────────────

def _generate_tts(text: str, language: str, out_path: str):
    client = OpenAI(api_key=settings.openai_api_key)
    voice = LANG_VOICE.get(language, "nova")
    response = client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
    )
    response.stream_to_file(out_path)


def _get_audio_duration(mp3_path: str) -> float:
    from mutagen.mp3 import MP3
    return MP3(mp3_path).info.length


# ── Video Assembly ────────────────────────────────────────────────────────────

def _assemble_video(segments_data: list, media_dir: str, output_path: str, language: str):
    from moviepy.editor import (
        AudioFileClip, CompositeVideoClip, TextClip,
        VideoFileClip, concatenate_videoclips, ColorClip,
    )

    TARGET_W, TARGET_H = 1080, 1920  # 9:16 vertical

    clips = []
    for i, seg in enumerate(segments_data):
        mp3_path = os.path.join(media_dir, f"audio_{i}.mp3")
        vid_path = os.path.join(media_dir, f"clip_{i}.mp4")
        audio_duration = _get_audio_duration(mp3_path)

        # Load stock clip or fallback to black background
        if os.path.exists(vid_path):
            try:
                base = (
                    VideoFileClip(vid_path)
                    .subclip(0, min(audio_duration, VideoFileClip(vid_path).duration))
                    .resize((TARGET_W, TARGET_H))
                    .set_duration(audio_duration)
                )
            except Exception:
                base = ColorClip((TARGET_W, TARGET_H), color=(10, 10, 20)).set_duration(audio_duration)
        else:
            base = ColorClip((TARGET_W, TARGET_H), color=(10, 10, 20)).set_duration(audio_duration)

        # Add audio
        base = base.set_audio(AudioFileClip(mp3_path))

        # Burn subtitles
        try:
            subtitle = (
                TextClip(
                    seg["text"],
                    fontsize=52,
                    color="white",
                    font="Arial-Bold",
                    stroke_color="black",
                    stroke_width=3,
                    method="caption",
                    size=(TARGET_W - 80, None),
                    align="center",
                )
                .set_position(("center", TARGET_H - 320))
                .set_duration(audio_duration)
            )
            base = CompositeVideoClip([base, subtitle])
        except Exception as e:
            logger.warning("Subtitle generation failed: %s", e)

        clips.append(base)

    final = concatenate_videoclips(clips, method="compose")
    try:
        final.write_videofile(output_path, fps=30, codec="libx264",
                              audio_codec="aac", threads=4, logger=None)
    except Exception:
        final.write_videofile(output_path, fps=30, codec="mpeg4",
                              audio_codec="aac", threads=4, logger=None)


# ── Main Run ──────────────────────────────────────────────────────────────────

def run(run_id: str, script_ids: Optional[List[int]] = None) -> List[int]:
    sb = get_client()
    log("video_producer", run_id, "info", "Video Producer gestartet")

    if script_ids:
        result = sb.table("video_scripts").select("*").in_("id", script_ids).eq("status", "READY").execute()
    else:
        result = sb.table("video_scripts").select("*").eq("status", "READY").execute()

    scripts = result.data
    if not scripts:
        log("video_producer", run_id, "warning", "Keine READY Scripts gefunden")
        return []

    produced_ids = []
    for script_row in scripts:
        sid = script_row["id"]
        lang = script_row["language"]
        script = script_row["script"] if isinstance(script_row["script"], dict) else json.loads(script_row["script"])
        segments = script["segments"]
        log("video_producer", run_id, "info",
            f"Produziere Video für Script #{sid} ({lang}): {len(segments)} Segmente")

        media_dir = os.path.join(settings.media_dir, f"script_{sid}")
        os.makedirs(media_dir, exist_ok=True)

        for i, seg in enumerate(segments):
            # TTS voiceover
            log("video_producer", run_id, "info",
                f"  [{lang}] Segment {i+1}/{len(segments)}: TTS...")
            mp3_path = os.path.join(media_dir, f"audio_{i}.mp3")
            _generate_tts(seg["text"], lang, mp3_path)

            # Stock video
            log("video_producer", run_id, "info",
                f"  [{lang}] Segment {i+1}/{len(segments)}: Stock-Video ({', '.join(seg.get('stock_keywords', []))})...")
            clip_url = _search_pexels_clip(
                seg.get("stock_keywords", ["psychology", "brain"]),
                seg.get("duration_s", 10),
            )
            if clip_url:
                vid_path = os.path.join(media_dir, f"clip_{i}.mp4")
                _download_file(clip_url, vid_path)

        output_path = os.path.join(media_dir, "final.mp4")
        log("video_producer", run_id, "info", f"  [{lang}] Montiere Video...")
        _assemble_video(segments, media_dir, output_path, lang)

        duration = int(script.get("total_duration_s", 0))
        result = sb.table("videos").insert({
            "script_id":  sid,
            "topic_id":   script_row["topic_id"],
            "language":   lang,
            "video_path": output_path,
            "duration_s": duration,
            "status":     "READY",
        }).execute()

        vid_id = result.data[0]["id"]
        produced_ids.append(vid_id)
        sb.table("video_scripts").update({"status": "PRODUCED"}).eq("id", sid).execute()
        log("video_producer", run_id, "info",
            f"  Video #{vid_id} ({lang}) fertig: {output_path}")

    log("video_producer", run_id, "info",
        f"Video Producer fertig — {len(produced_ids)} Videos produziert")
    return produced_ids
