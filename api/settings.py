from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AppConfig

router = APIRouter()

ALLOWED_KEYS = {
    "niche_keywords",
    "schedule_cron",
    "max_topics_per_run",
    "tiktok_uploader_type",
    "last_insights",
}


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(AppConfig).all()
    return {r.key: r.value for r in rows}


@router.put("")
def update_settings(payload: dict, db: Session = Depends(get_db)):
    for key, value in payload.items():
        row = db.query(AppConfig).filter_by(key=key).first()
        if row:
            row.value = str(value)
        else:
            db.add(AppConfig(key=key, value=str(value)))
    db.commit()
    return {"ok": True, "updated": list(payload.keys())}
