"""
Agent 1 – Topic Scout
Finds 3 viral psychology topics per day using Claude.
Stores them in the `topics` table.
"""
import json
import logging
from typing import List

import anthropic

from config import settings
from supabase_client import get_client, get_config, log

logger = logging.getLogger(__name__)


def _find_topics(niche: str, count: int) -> List[dict]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=(
            "You are a viral short-form video content strategist. "
            "You find psychology topics that perform exceptionally well on TikTok, Instagram Reels and YouTube Shorts. "
            "Topics should be surprising, counterintuitive, or emotionally engaging. "
            "Respond only with valid JSON, no markdown."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Find {count} viral psychology topics for short-form video (60s max).\n"
                f"Niche: {niche}\n\n"
                "Each topic should:\n"
                "- Be a specific psychological concept or phenomenon\n"
                "- Have a surprising or counterintuitive angle\n"
                "- Work well explained in 45-60 seconds\n"
                "- Appeal to a broad international audience\n\n"
                "Return JSON array:\n"
                '[{"title": "Why your brain lies to you about memories", '
                '"hook": "90% of your memories are completely fake", '
                '"key_facts": ["fact1", "fact2", "fact3"], '
                '"virality_score": 9.2}]'
            ),
        }],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def run(run_id: str) -> List[int]:
    sb = get_client()
    log("topic_scout", run_id, "info", "Topic Scout gestartet")

    niche = get_config("niche", "psychology")
    count = int(get_config("topics_per_day", "3"))

    log("topic_scout", run_id, "info", f"Suche {count} virale {niche}-Themen...")
    topics = _find_topics(niche, count)

    created_ids = []
    for t in topics:
        result = sb.table("topics").insert({
            "title":     t["title"],
            "niche":     niche,
            "hook":      t.get("hook", ""),
            "key_facts": json.dumps(t.get("key_facts", [])),
            "status":    "PENDING",
        }).execute()
        tid = result.data[0]["id"]
        created_ids.append(tid)
        log("topic_scout", run_id, "info",
            f"Topic #{tid}: '{t['title']}' (Virality {t.get('virality_score', '?')})")

    log("topic_scout", run_id, "info", f"Topic Scout fertig — {len(created_ids)} Themen erstellt")
    return created_ids
