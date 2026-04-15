"""
Agent 1 – Trend Scout
Pulls trending topics from Google Trends, Reddit, and TikTok Creative Center,
then uses Claude to score and rank them for TikTok virality.
"""
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List

import anthropic
import requests

from config import settings
from supabase_client import get_client, get_config, set_config, log

logger = logging.getLogger(__name__)

TIKTOK_CC_URL = (
    "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
    "?period=7&page=1&limit=20&country_code=US"
)


def _cache_valid() -> bool:
    fetched_at_str = get_config("trends_fetched_at")
    if not fetched_at_str:
        return False
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
        return datetime.now(timezone.utc) - fetched_at < timedelta(hours=2)
    except ValueError:
        return False


def _fetch_google_trends(keywords: List[str]) -> List[str]:
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=360)
        topics = []
        for kw in keywords[:3]:
            time.sleep(5)
            pytrends.build_payload([kw], cat=0, timeframe="now 7-d")
            related = pytrends.related_queries()
            if kw in related and related[kw]["rising"] is not None:
                rising = related[kw]["rising"]
                topics.extend(rising["query"].head(5).tolist())
        return list(set(topics))
    except Exception as e:
        logger.warning("pytrends failed: %s", e)
        return []


def _fetch_reddit(keywords: List[str]) -> List[str]:
    try:
        if not settings.reddit_client_id:
            return []
        import praw
        reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
            check_for_async=False,
        )
        subreddits = ["fitness", "motivation", "technology", "personalfinance", "mindset"]
        topics = []
        for sub in subreddits[:3]:
            try:
                for post in reddit.subreddit(sub).hot(limit=10):
                    if not post.stickied:
                        topics.append(post.title)
            except Exception:
                pass
        return topics
    except Exception as e:
        logger.warning("Reddit fetch failed: %s", e)
        return []


def _fetch_tiktok_cc() -> List[str]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        resp = requests.get(TIKTOK_CC_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [
            f"#{item['hashtag_name']}"
            for item in data.get("data", {}).get("list", [])
            if item.get("hashtag_name")
        ][:15]
    except Exception as e:
        logger.warning("TikTok Creative Center fetch failed: %s", e)
        return []


def _score_with_claude(topics: List[str], niche: str, insights: str) -> List[dict]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    topics_text = "\n".join(f"- {t}" for t in topics[:40])
    insights_section = f"\n\nPrevious content insights:\n{insights}" if insights else ""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=(
            "You are an expert TikTok content strategist. Score trending topics for virality "
            "potential on TikTok. Always respond with valid JSON only, no markdown."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Niche: {niche}\n\nRaw trending topics:\n{topics_text}{insights_section}\n\n"
                "Select the top 5 topics adapted for TikTok short-form video.\n"
                'Return JSON array: [{"topic": "...", "score": 8.5, "rationale": "...", "hook_idea": "..."}]'
            ),
        }],
    )
    return json.loads(response.content[0].text.strip())


def run(run_id: str) -> List[int]:
    sb = get_client()
    log("trend_scout", run_id, "info", "Trend Scout gestartet")

    niche_raw = get_config("niche_keywords", "fitness,motivation")
    niche_keywords = [k.strip() for k in niche_raw.split(",") if k.strip()]
    insights = get_config("last_insights", "")
    max_topics = int(get_config("max_topics_per_run", "3"))
    created_ids = []

    if _cache_valid():
        log("trend_scout", run_id, "info", "Trend-Cache noch gültig (<2h), überspringe Fetch")
        return created_ids

    log("trend_scout", run_id, "info", f"Fetche Trends für Nische: {niche_raw}")

    google_topics = _fetch_google_trends(niche_keywords)
    log("trend_scout", run_id, "info", f"Google Trends: {len(google_topics)} Themen")

    reddit_topics = _fetch_reddit(niche_keywords)
    log("trend_scout", run_id, "info", f"Reddit: {len(reddit_topics)} Themen")

    tiktok_topics = _fetch_tiktok_cc()
    log("trend_scout", run_id, "info", f"TikTok Creative Center: {len(tiktok_topics)} Themen")

    all_topics = list(set(google_topics + reddit_topics + tiktok_topics))
    if not all_topics:
        all_topics = [f"{kw} tips for beginners" for kw in niche_keywords]
        log("trend_scout", run_id, "warning", "Keine externen Trends gefunden, nutze Fallback-Themen")

    log("trend_scout", run_id, "info", f"Bewerte {len(all_topics)} Themen mit Claude...")
    scored = _score_with_claude(all_topics, niche_raw, insights)
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)

    set_config("trends_fetched_at", datetime.now(timezone.utc).isoformat())

    for item in scored[:max_topics]:
        result = sb.table("content_pieces").insert({
            "niche": niche_raw,
            "trend_topic": item["topic"],
            "trend_score": item["score"],
            "status": "TREND_SCORED",
        }).execute()
        piece_id = result.data[0]["id"]
        created_ids.append(piece_id)
        log("trend_scout", run_id, "info",
            f"ContentPiece #{piece_id} erstellt: '{item['topic']}' (Score {item['score']})")

    log("trend_scout", run_id, "info", f"Trend Scout fertig. {len(created_ids)} Stücke erstellt.")
    return created_ids
