from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.database import get_db
from app.models.database import Feedback

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Submit user feedback on a RAG response.

    Stores the question, answer, citations, and rating in the database.
    """
    try:
        # Convert citations to JSON-serializable format
        citations_data = [c.model_dump() for c in request.citations]

        # Create feedback record
        feedback = Feedback(
            session_id=request.session_id,
            question=request.question,
            answer=request.answer,
            citations=citations_data,
            rating=request.rating
        )

        db.add(feedback)
        await db.commit()

        rating_text = "positive" if request.rating > 0 else "negative"
        logger.info(f"Feedback received: {rating_text} (session: {request.session_id})")

        return FeedbackResponse(
            status="success",
            message="Thank you for your feedback!"
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to store feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to store feedback")
