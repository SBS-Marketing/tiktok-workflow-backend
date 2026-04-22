"""
Agent 2 – Script Writer
For each topic, generates scripts in DE, EN, ES, FR.
Each script has segments with spoken text + stock video search keywords.
"""
import json
import logging
from typing import List, Optional

import anthropic

from config import settings
from supabase_client import get_client, get_config, log

logger = logging.getLogger(__name__)

LANGUAGES = {
    "DE": {"name": "German",  "locale": "de"},
    "EN": {"name": "English", "locale": "en"},
    "ES": {"name": "Spanish", "locale": "es"},
    "FR": {"name": "French",  "locale": "fr"},
}

SCRIPT_SCHEMA = """{
  "hook": "<opening line in target language, max 10 words, stops the scroll>",
  "segments": [
    {
      "text": "<spoken text in target language, 1-3 sentences>",
      "stock_keywords": ["keyword1", "keyword2"],
      "duration_s": <8-15>
    }
  ],
  "cta": "<call-to-action in target language, e.g. 'Follow for more psychology facts!'>",
  "hashtags": ["#Psychology", "#MindFacts"],
  "total_duration_s": <sum of segments>
}"""


def _write_script(topic: dict, language: str) -> dict:
    lang_info = LANGUAGES[language]
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=(
            f"You are a viral short-form video scriptwriter. "
            f"Write engaging psychology content in {lang_info['name']}. "
            f"The script will be used with stock footage and voiceover. "
            f"Respond only with valid JSON, no markdown."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Write a 45-60 second video script in {lang_info['name']} for:\n\n"
                f"Topic: {topic['title']}\n"
                f"Hook idea: {topic.get('hook', '')}\n"
                f"Key facts: {', '.join(json.loads(topic.get('key_facts') or '[]'))}\n\n"
                f"Requirements:\n"
                f"- 4-6 segments of 8-15 seconds each\n"
                f"- Each segment needs 2-3 stock video search keywords (in English, for Pexels)\n"
                f"- Engaging, educational, surprising tone\n"
                f"- Written entirely in {lang_info['name']}\n\n"
                f"Return ONLY this JSON schema:\n{SCRIPT_SCHEMA}"
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


def run(run_id: str, topic_ids: Optional[List[int]] = None) -> List[int]:
    sb = get_client()
    log("script_writer", run_id, "info", "Script Writer gestartet")

    languages_str = get_config("languages", "DE,EN,ES,FR")
    languages = [l.strip() for l in languages_str.split(",") if l.strip()]

    # Fetch pending topics
    if topic_ids:
        result = sb.table("topics").select("*").in_("id", topic_ids).eq("status", "PENDING").execute()
    else:
        result = sb.table("topics").select("*").eq("status", "PENDING").execute()

    topics = result.data
    if not topics:
        log("script_writer", run_id, "warning", "Keine PENDING Topics gefunden")
        return []

    created_ids = []
    for topic in topics:
        log("script_writer", run_id, "info",
            f"Schreibe Scripts für Topic #{topic['id']}: '{topic['title']}'")

        for lang in languages:
            try:
                script = _write_script(topic, lang)
                result = sb.table("video_scripts").insert({
                    "topic_id": topic["id"],
                    "language": lang,
                    "script":   script,
                    "status":   "READY",
                }).execute()
                sid = result.data[0]["id"]
                created_ids.append(sid)
                log("script_writer", run_id, "info",
                    f"  Script #{sid} ({lang}): {len(script['segments'])} Segmente, "
                    f"~{script.get('total_duration_s', '?')}s")
            except Exception as e:
                log("script_writer", run_id, "error",
                    f"  Script ({lang}) für Topic #{topic['id']} fehlgeschlagen: {e}")

        # Mark topic as scripted
        sb.table("topics").update({"status": "SCRIPTED"}).eq("id", topic["id"]).execute()

    log("script_writer", run_id, "info",
        f"Script Writer fertig — {len(created_ids)} Scripts in {len(languages)} Sprachen erstellt")
    return created_ids
