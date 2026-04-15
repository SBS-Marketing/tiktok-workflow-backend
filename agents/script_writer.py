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

    from supabase_client import get_config
    zodiac = get_config("zodiac_sign", "Steinbock")
    target_date = get_config("horoscope_date", "heute")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=(
            "Du bist ein erfahrener Astrologe und viraler TikTok-Creator. "
            "Du schreibst mitreißende Tageshoroskop-Videos auf Deutsch. "
            "Dein Stil ist mystisch, warm und inspirierend. "
            "Antworte ausschließlich mit validem JSON, kein Markdown."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Schreibe ein TikTok-Tageshoroskop-Video-Script für:\n"
                f"- Sternzeichen: {zodiac}\n"
                f"- Datum: {target_date}\n"
                f"- Thema: '{piece['trend_topic']}'\n"
                f"- Zieldauer: 45-60 Sekunden, 4-6 Segmente\n\n"
                f"Das Script soll auf Deutsch sein. Beginne mit einem Hook der sofort fesselt "
                f"(z.B. '✨ {zodiac}! Was die Sterne heute für dich bereithalten...'). "
                f"Jedes Segment braucht einen konkreten DALL-E Bildprompt (vertikal 9:16, mystisch).\n\n"
                f"Antworte NUR mit diesem JSON-Schema:\n{SCRIPT_SCHEMA}"
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
