from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index, JSON
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import settings


class KBChunk(Base):
    """Knowledge base chunk with vector embedding."""

    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(64), unique=True, nullable=False, index=True)
    source_file = Column(String(255), nullable=False)
    section_heading = Column(Text, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.embedding_dimensions), nullable=False)
    kb_version = Column(Integer, nullable=False, index=True)
    is_guideline = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            'idx_kb_chunks_embedding_hnsw',
            'embedding',
            postgresql_using='hnsw',
            postgresql_with={'m': 16, 'ef_construction': 64},
            postgresql_ops={'embedding': 'vector_cosine_ops'}
        ),
    )


class Feedback(Base):
    """User feedback on RAG responses."""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    rating = Column(Integer, nullable=False)  # 1 for thumbs up, -1 for thumbs down
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
