from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base


class ChatAnalytics(Base):
    """One row per chat request for analytics tracking."""

    __tablename__ = "chat_analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    response_source = Column(String(32), index=True, nullable=False)
    route_taken = Column(String(32), nullable=False)
    confidence = Column(String(16), nullable=False)
    max_similarity = Column(Float, nullable=True)
    chunk_count = Column(Integer, nullable=False, default=0)
    is_knowledge_gap = Column(Boolean, index=True, nullable=False, default=False)
    patient_type = Column(String(16), nullable=True)
    sentiment = Column(String(16), nullable=True, index=True)
    response_time_ms = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_analytics_created_source", "created_at", "response_source"),
        Index("ix_analytics_gap_created", "is_knowledge_gap", "created_at"),
    )
