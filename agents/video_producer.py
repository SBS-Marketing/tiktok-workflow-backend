"""
Agent 3 – Video Producer & Uploader
Generates images (DALL-E 3), TTS audio (ElevenLabs), assembles the video
with MoviePy, adds subtitles, and uploads via the configured uploader.
"""
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import uuid4

import requests
from openai import OpenAI

from config import settings
from supabase_client import get_client, get_config, log

logger = logging.getLogger(__name__)


class TikTokUploaderBase(ABC):
    @abstractmethod
    def upload(self, video_path: str, caption: str, hashtags: List[str]) -> str: ...


class ZernioUploader(TikTokUploaderBase):
    def upload(self, video_path: str, caption: str, hashtags: List[str]) -> str:
        with open(video_path, "rb") as f:
            resp = requests.post(
                settings.zernio_api_url,
                headers={"Authorization": f"Bearer {settings.zernio_api_key}"},
                files={"video": f},
                data={"caption": caption, "hashtags": " ".join(hashtags)},
                timeout=120,
            )
        resp.raise_for_status()
        data = resp.json()
        return data.get("tiktok_url", f"https://tiktok.com/uploaded/{uuid4()}")


class PlaceholderUploader(TikTokUploaderBase):
    def upload(self, video_path: str, caption: str, hashtags: List[str]) -> str:
        logger.info("[video_producer] Placeholder upload – kein echter TikTok-Post")
        return f"https://tiktok.com/placeholder/{uuid4()}"


def _get_uploader() -> TikTokUploaderBase:
    uploader_type = get_config("tiktok_uploader_type", "placeholder")
    if uploader_type == "zernio" and settings.zernio_api_key:
        return ZernioUploader()
    return PlaceholderUploader()


def _generate_image(client: OpenAI, prompt: str, out_path: str):
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt + " Vertical 9:16 aspect ratio, photorealistic, vibrant colors.",
        size="1024x1792",
        quality="standard",
        n=1,
    )
    img_data = requests.get(response.data[0].url, timeout=30).content
    with open(out_path, "wb") as f:
        f.write(img_data)


def _generate_tts_elevenlabs(text: str, out_path: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
    resp = requests.post(
        url,
        headers={"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=30,
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)


def _generate_tts_openai(text: str, out_path: str):
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",   # warm, feminine — gut für Horoskope
        input=text,
    )
    response.stream_to_file(out_path)


def _generate_tts(text: str, out_path: str):
    """ElevenLabs with automatic fallback to OpenAI TTS."""
    if settings.elevenlabs_api_key:
        try:
            _generate_tts_elevenlabs(text, out_path)
            return
        except Exception as e:
            logger.warning("ElevenLabs fehlgeschlagen (%s) – nutze OpenAI TTS als Fallback", e)
    _generate_tts_openai(text, out_path)


def _get_audio_duration(mp3_path: str) -> float:
    from mutagen.mp3 import MP3
    return MP3(mp3_path).info.length


def _assemble_video(segments_data: list, media_dir: str, output_path: str):
    from moviepy.editor import (
        AudioFileClip, CompositeVideoClip, ImageClip, TextClip, concatenate_videoclips,
    )
    clips = []
    for i, seg in enumerate(segments_data):
        img_path = os.path.join(media_dir, f"img_{i}.png")
        mp3_path = os.path.join(media_dir, f"audio_{i}.mp3")
        duration = _get_audio_duration(mp3_path)
        clip = ImageClip(img_path).set_duration(duration).set_audio(AudioFileClip(mp3_path))
        try:
            txt = (
                TextClip(seg["text"], fontsize=38, color="white", font="Arial-Bold",
                         stroke_color="black", stroke_width=2, method="caption",
                         size=(clip.w - 80, None))
                .set_position(("center", "bottom")).set_duration(duration).margin(bottom=80, opacity=0)
            )
            clip = CompositeVideoClip([clip, txt])
        except Exception as e:
            logger.warning("TextClip fehlgeschlagen: %s", e)
        clips.append(clip)

    final = concatenate_videoclips(clips, method="compose")
    try:
        final.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac", threads=4, logger=None)
    except Exception:
        final.write_videofile(output_path, fps=24, codec="mpeg4", audio_codec="aac", threads=4, logger=None)


def run(run_id: str, content_id: Optional[int] = None) -> int:
    sb = get_client()

    if content_id:
        result = sb.table("content_pieces").select("*").eq("id", content_id).eq("status", "SCRIPT_READY").single().execute()
        pieces = [result.data] if result.data else []
    else:
        result = sb.table("content_pieces").select("*").eq("status", "SCRIPT_READY").limit(1).execute()
        pieces = result.data

    if not pieces:
        log("video_producer", run_id, "warning", "Kein SCRIPT_READY ContentPiece gefunden, überspringe")
        return -1

    piece = pieces[0]
    log("video_producer", run_id, "info", f"Produziere Video für #{piece['id']}: '{piece['trend_topic']}'")

    script = json.loads(piece["script"])
    segments = script["segments"]
    cta_text = script.get("cta", "")
    hashtags = script.get("hashtags", [])

    if cta_text:
        segments.append({
            "text": cta_text,
            "image_prompt": "Vibrant social media follow button on dark background",
            "duration_s": 3,
        })

    media_dir = os.path.join(settings.media_dir, str(piece["id"]))
    os.makedirs(media_dir, exist_ok=True)
    openai_client = OpenAI(api_key=settings.openai_api_key)

    for i, seg in enumerate(segments):
        log("video_producer", run_id, "info", f"  Segment {i+1}/{len(segments)}: Bild wird generiert...")
        _generate_image(openai_client, seg["image_prompt"], os.path.join(media_dir, f"img_{i}.png"))
        time.sleep(12)

        log("video_producer", run_id, "info", f"  Segment {i+1}/{len(segments)}: Audio wird generiert...")
        _generate_tts(seg["text"], os.path.join(media_dir, f"audio_{i}.mp3"))

    output_path = os.path.join(media_dir, "final.mp4")
    log("video_producer", run_id, "info", "Video wird mit MoviePy montiert...")
    _assemble_video(segments, media_dir, output_path)

    caption = f"{script.get('hook', piece['trend_topic'])} {' '.join(hashtags)}"
    uploader = _get_uploader()
    log("video_producer", run_id, "info", f"Upload via {type(uploader).__name__}...")
    tiktok_url = uploader.upload(output_path, caption, hashtags)

    sb.table("content_pieces").update({
        "video_path": output_path,
        "tiktok_url": tiktok_url,
        "status": "UPLOADED",
    }).eq("id", piece["id"]).execute()

    log("video_producer", run_id, "info", f"Video hochgeladen: {tiktok_url}")
    return piece["id"]
