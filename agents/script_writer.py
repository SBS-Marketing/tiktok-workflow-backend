"""
Agent 2 – Script Writer
Takes the top TREND_SCORED ContentPiece and uses Claude to generate
a structured TikTok script in strict JSON format.
"""
import json
import logging
from typing import Optional

import anthropic

from config import settings
from supabase_client import get_client, log

logger = logging.getLogger(__name__)

SCRIPT_SCHEMA = """{
  "hook": "<5-second opening line that stops the scroll>",
  "segments": [
    {
      "text": "<spoken text for this segment>",
      "image_prompt": "<DALL-E 3 image prompt, photorealistic, vertical 9:16>",
      "duration_s": <integer seconds, 4-12>
    }
  ],
  "cta": "<call-to-action line at the end>",
  "hashtags": ["#tag1", "#tag2"],
  "total_duration_s": <sum of all segment durations>
}"""


def run(run_id: str, content_id: Optional[int] = None) -> int:
    sb = get_client()

    if content_id:
        result = sb.table("content_pieces").select("*").eq("id", content_id).eq("status", "TREND_SCORED").single().execute()
    else:
        result = sb.table("content_pieces").select("*").eq("status", "TREND_SCORED").order("trend_score", desc=True).limit(1).execute()
        result.data = result.data[:1]

    if not result.data:
        log("script_writer", run_id, "warning", "Kein TREND_SCORED ContentPiece gefunden, überspringe")
        return -1

    piece = result.data[0]
    log("script_writer", run_id, "info", f"Schreibe Script für #{piece['id']}: '{piece['trend_topic']}'")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=(
            "You are a viral TikTok scriptwriter. You specialize in short-form video scripts "
            "that hook viewers in the first 3 seconds. Always output valid JSON only, no markdown."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Write a TikTok script for: '{piece['trend_topic']}'\n"
                f"Niche: {piece['niche']}\n"
                f"Target duration: 30-60 seconds, 4-7 segments.\n\n"
                f"Return ONLY this JSON schema:\n{SCRIPT_SCHEMA}"
            ),
        }],
    )

    raw = response.content[0].text.strip()
    script_data = json.loads(raw)
    assert "hook" in script_data and "segments" in script_data and len(script_data["segments"]) > 0

    sb.table("content_pieces").update({
        "script": json.dumps(script_data, ensure_ascii=False),
        "status": "SCRIPT_READY",
    }).eq("id", piece["id"]).execute()

    segment_count = len(script_data["segments"])
    duration = script_data.get("total_duration_s", "?")
    log("script_writer", run_id, "info",
        f"Script fertig für #{piece['id']}: {segment_count} Segmente, ~{duration}s")
    return piece["id"]
