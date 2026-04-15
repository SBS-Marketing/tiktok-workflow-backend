"""
Agent 1 – Trend Scout (Horoscope Mode)
Uses Claude to generate daily horoscope content angles for the selected
zodiac sign and date. No external scraping needed.
"""
import json
import logging
from datetime import date
from typing import List

import anthropic

from config import settings
from supabase_client import get_client, get_config, log

logger = logging.getLogger(__name__)

ZODIAC_SIGNS = [
    "Widder", "Stier", "Zwillinge", "Krebs", "Löwe", "Jungfrau",
    "Waage", "Skorpion", "Schütze", "Steinbock", "Wassermann", "Fische",
]

ANGLES = ["Liebe & Beziehungen", "Karriere & Finanzen", "Energie & Wohlbefinden"]


def _generate_topics(zodiac: str, target_date: str, max_topics: int) -> List[dict]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "Du bist ein Astrologe und TikTok-Content-Stratege. "
            "Antworte ausschließlich mit validem JSON, kein Markdown."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Erstelle {max_topics} Horoskop-Content-Ideen für:\n"
                f"- Sternzeichen: {zodiac}\n"
                f"- Datum: {target_date}\n"
                f"- Mögliche Themen-Winkel: {', '.join(ANGLES)}\n\n"
                "Jede Idee soll einen spezifischen Winkel haben, der emotional anspricht.\n"
                "Antworte als JSON-Array:\n"
                '[{"topic": "Steinbock Tageshoroskop – Liebe 15. April", "score": 8.5, "angle": "Liebe & Beziehungen"}]'
            ),
        }],
    )

    raw = response.content[0].text.strip()
    items = json.loads(raw)
    return items[:max_topics]


def run(run_id: str) -> List[int]:
    sb = get_client()
    log("trend_scout", run_id, "info", "Trend Scout (Horoskop) gestartet")

    zodiac = get_config("zodiac_sign", "Steinbock")
    target_date = get_config("horoscope_date", date.today().isoformat())
    max_topics = int(get_config("max_topics_per_run", "1"))

    log("trend_scout", run_id, "info", f"Generiere Horoskop-Themen für {zodiac}, {target_date}")

    topics = _generate_topics(zodiac, target_date, max_topics)
    created_ids = []

    for item in topics:
        result = sb.table("content_pieces").insert({
            "niche": f"horoscope_{zodiac.lower()}",
            "trend_topic": item["topic"],
            "trend_score": item.get("score", 8.0),
            "status": "TREND_SCORED",
        }).execute()
        piece_id = result.data[0]["id"]
        created_ids.append(piece_id)
        log("trend_scout", run_id, "info",
            f"ContentPiece #{piece_id} erstellt: '{item['topic']}'")

    log("trend_scout", run_id, "info", f"Trend Scout fertig. {len(created_ids)} Themen erstellt.")
    return created_ids
