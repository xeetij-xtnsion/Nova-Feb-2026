from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging
import sys
from pathlib import Path

# Add scripts directory to path to import ingest logic
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.ingest_kb import ingest_all

logger = logging.getLogger(__name__)

router = APIRouter()


class IngestRequest(BaseModel):
    """Request schema for ingest endpoint."""
    sources_dir: str = Field(default="kb/sources", description="Directory containing .docx files")
    kb_version: Optional[int] = Field(None, description="KB version number (defaults to config)")
    background: bool = Field(default=False, description="Run ingestion in background")


class IngestResponse(BaseModel):
    """Response schema for ingest endpoint."""
    status: str
    message: str


async def run_ingestion(sources_dir: str, kb_version: Optional[int]):
    """Background task for running ingestion."""
    try:
        await ingest_all(sources_dir, kb_version)
        logger.info("Background ingestion completed successfully")
    except Exception as e:
        logger.error(f"Background ingestion failed: {e}")


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: IngestRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger knowledge base ingestion.

    Can run synchronously or as a background task.
    """
    try:
        if request.background:
            # Run in background
            background_tasks.add_task(
                run_ingestion,
                request.sources_dir,
                request.kb_version
            )
            logger.info("Ingestion started in background")
            return IngestResponse(
                status="started",
                message=f"Ingestion started in background for {request.sources_dir}"
            )
        else:
            # Run synchronously
            logger.info(f"Starting ingestion from {request.sources_dir}")
            await ingest_all(request.sources_dir, request.kb_version)
            return IngestResponse(
                status="completed",
                message=f"Ingestion completed successfully from {request.sources_dir}"
            )

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
