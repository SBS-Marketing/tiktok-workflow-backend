"""
Agent 1 – Horoscope Generator
Uses Claude to generate a full daily horoscope reading for the selected
zodiac sign and date. Stores the structured horoscope as JSON in content_pieces.
"""
import json
import logging
from datetime import date
from typing import List

import anthropic

from config import settings
from supabase_client import get_client, get_config, log

logger = logging.getLogger(__name__)

HOROSCOPE_SCHEMA = """{
  "zodiac": "<Sternzeichen>",
  "date": "<Datum>",
  "general": "<Allgemeine Tagesenergie, 2-3 Sätze, inspirierend>",
  "love": "<Liebes- & Beziehungshoroskop, 2-3 Sätze>",
  "career": "<Karriere & Finanzen, 2-3 Sätze>",
  "energy_level": <Zahl 1-10, heutige Energie>,
  "lucky_number": <Glückszahl>,
  "lucky_color": "<Glücksfarbe>",
  "affirmation": "<Tages-Affirmation, ein kraftvoller Satz>",
  "planetary_influence": "<Welcher Planet dominiert heute und was bedeutet das>"
}"""


def _generate_horoscope(zodiac: str, target_date: str) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=(
            "Du bist ein erfahrener Astrologe mit tiefem Wissen über Planeten, Sternzeichen "
            "und kosmische Energien. Du schreibst einfühlsame, inspirierende Tageshoroskope "
            "auf Deutsch. Deine Horoskope sind konkret, emotional und motivierend. "
            "Antworte ausschließlich mit validem JSON, kein Markdown."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Erstelle ein vollständiges Tageshoroskop für:\n"
                f"- Sternzeichen: {zodiac}\n"
                f"- Datum: {target_date}\n\n"
                f"Berücksichtige typische astrologische Energien für dieses Datum. "
                f"Sei spezifisch, emotional und inspirierend.\n\n"
                f"Antworte NUR mit diesem JSON-Schema:\n{HOROSCOPE_SCHEMA}"
            ),
        }],
    )

    raw = response.content[0].text.strip()
    return json.loads(raw)


def run(run_id: str) -> List[int]:
    sb = get_client()
    log("trend_scout", run_id, "info", "Horoskop-Generator gestartet")

    zodiac = get_config("zodiac_sign", "Steinbock")
    target_date = get_config("horoscope_date", date.today().isoformat())
    max_videos = int(get_config("max_topics_per_run", "1"))

    log("trend_scout", run_id, "info", f"Generiere Tageshoroskop für {zodiac} am {target_date}")

    created_ids = []

    for i in range(max_videos):
        # For multiple videos, vary the focus angle
        angle_hint = ""
        if max_videos > 1:
            angles = ["allgemein", "Liebe", "Karriere"]
            angle = angles[i % len(angles)]
            angle_hint = f" (Fokus: {angle})"

        horoscope = _generate_horoscope(zodiac, target_date)

        title = f"{zodiac} Tageshoroskop {target_date}{angle_hint}"

        result = sb.table("content_pieces").insert({
            "niche": f"horoscope",
            "trend_topic": json.dumps(horoscope, ensure_ascii=False),
            "trend_score": horoscope.get("energy_level", 8.0),
            "status": "TREND_SCORED",
        }).execute()

        piece_id = result.data[0]["id"]
        created_ids.append(piece_id)
        log("trend_scout", run_id, "info",
            f"Horoskop #{piece_id} generiert: {title} "
            f"(Energie {horoscope.get('energy_level')}/10, "
            f"Glückszahl {horoscope.get('lucky_number')})")

    log("trend_scout", run_id, "info", f"Horoskop-Generator fertig. {len(created_ids)} Horoskope erstellt.")
    return created_ids
