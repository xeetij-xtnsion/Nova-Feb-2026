from pydantic import BaseModel, Field
from typing import Optional, List


class Citation(BaseModel):
    """Citation metadata."""
    chunk_id: str
    source_file: str
    section_heading: str
    chunk_index: int


class ChatRequest(BaseModel):
    """Request schema for chat endpoint."""
    message: str = Field(..., min_length=1, description="User's question")
    session_id: Optional[str] = Field(None, description="Optional session ID for grouping")


class ChatResponse(BaseModel):
    """Response schema for chat endpoint."""
    answer: str = Field(..., description="Generated answer")
    citations: List[Citation] = Field(default_factory=list, description="Source citations")
    session_id: Optional[str] = Field(None, description="Session ID if provided")
    confidence: str = Field(..., description="Confidence level: 'high' or 'low'")
    max_similarity: Optional[float] = Field(None, description="Maximum similarity score from retrieval")
