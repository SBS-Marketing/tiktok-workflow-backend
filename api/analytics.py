from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Analytics, ContentPiece

router = APIRouter()


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db)):
    total_videos = db.query(ContentPiece).filter(ContentPiece.status == "ANALYTICS_COLLECTED").count()
    agg = db.query(
        func.sum(Analytics.views).label("total_views"),
        func.sum(Analytics.likes).label("total_likes"),
        func.sum(Analytics.comments).label("total_comments"),
        func.sum(Analytics.shares).label("total_shares"),
        func.avg(Analytics.views).label("avg_views"),
    ).first()

    total_views = agg.total_views or 0
    total_interactions = (agg.total_likes or 0) + (agg.total_comments or 0) + (agg.total_shares or 0)
    avg_engagement = round(total_interactions / total_views * 100, 2) if total_views > 0 else 0.0

    return {
        "total_videos": total_videos,
        "total_views": total_views,
        "total_likes": agg.total_likes or 0,
        "total_comments": agg.total_comments or 0,
        "total_shares": agg.total_shares or 0,
        "avg_views": round(agg.avg_views or 0, 0),
        "avg_engagement_rate": avg_engagement,
    }


@router.get("/{content_id}")
def analytics_for_video(content_id: int, db: Session = Depends(get_db)):
    piece = db.query(ContentPiece).filter_by(id=content_id).first()
    if not piece:
        raise HTTPException(status_code=404, detail="ContentPiece not found")

    rows = (
        db.query(Analytics)
        .filter_by(content_id=content_id)
        .order_by(Analytics.fetched_at.asc())
        .all()
    )
    return {
        "content_id": content_id,
        "trend_topic": piece.trend_topic,
        "tiktok_url": piece.tiktok_url,
        "metrics": [
            {
                "views": r.views,
                "likes": r.likes,
                "comments": r.comments,
                "shares": r.shares,
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
            }
            for r in rows
        ],
    }


@router.get("")
def analytics_list(limit: int = 50, db: Session = Depends(get_db)):
    rows = (
        db.query(Analytics, ContentPiece.trend_topic, ContentPiece.niche)
        .join(ContentPiece, Analytics.content_id == ContentPiece.id)
        .order_by(Analytics.fetched_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "analytics_id": r.Analytics.id,
            "content_id": r.Analytics.content_id,
            "trend_topic": r.trend_topic,
            "niche": r.niche,
            "views": r.Analytics.views,
            "likes": r.Analytics.likes,
            "comments": r.Analytics.comments,
            "shares": r.Analytics.shares,
            "fetched_at": r.Analytics.fetched_at.isoformat() if r.Analytics.fetched_at else None,
        }
        for r in rows
    ]
