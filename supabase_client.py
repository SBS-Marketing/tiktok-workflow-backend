"""
Supabase client — single shared instance for all agents and API routers.
"""
from typing import Optional
from supabase import create_client, Client
from config import settings

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def get_config(key: str, fallback: str = "") -> str:
    try:
        result = get_client().table("app_config").select("value").eq("key", key).execute()
        if result.data:
            return result.data[0].get("value") or fallback
        return fallback
    except Exception:
        return fallback


def set_config(key: str, value: str):
    get_client().table("app_config").upsert({"key": key, "value": value}).execute()


def log(agent_name: str, run_id: str, level: str, message: str):
    import logging
    logging.getLogger(agent_name).info("[%s] %s", agent_name, message)
    try:
        get_client().table("agent_logs").insert({
            "agent_name": agent_name,
            "level": level,
            "message": message,
            "run_id": run_id,
        }).execute()
    except Exception:
        pass
