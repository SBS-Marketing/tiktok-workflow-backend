from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class ContentPiece(Base):
    __tablename__ = "content_pieces"

    id = Column(Integer, primary_key=True, index=True)
    niche = Column(String, nullable=False)
    trend_topic = Column(String, nullable=False)
    trend_score = Column(Float, default=0.0)
    script = Column(Text, nullable=True)
    video_path = Column(String, nullable=True)
    tiktok_url = Column(String, nullable=True)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)

    analytics = relationship("Analytics", back_populates="content", cascade="all, delete-orphan")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String, nullable=False)
    level = Column(String, default="info")
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    run_id = Column(String, nullable=True)


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, index=True)
    content_id = Column(Integer, ForeignKey("content_pieces.id"))
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    content = relationship("ContentPiece", back_populates="analytics")


class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String, primary_key=True)
    value = Column(Text)
