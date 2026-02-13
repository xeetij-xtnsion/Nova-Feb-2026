from pydantic import BaseModel, Field
from typing import Optional, List
from app.schemas.chat import Citation


class FeedbackRequest(BaseModel):
    """Request schema for feedback endpoint."""
    session_id: Optional[str] = Field(None, description="Optional session ID")
    question: str = Field(..., description="Original question")
    answer: str = Field(..., description="Answer that was provided")
    citations: List[Citation] = Field(default_factory=list, description="Citations from answer")
    rating: int = Field(..., description="Rating: 1 for thumbs up, -1 for thumbs down")


class FeedbackResponse(BaseModel):
    """Response schema for feedback endpoint."""
    status: str = Field(..., description="Status message")
    message: str = Field(..., description="Human-readable message")
