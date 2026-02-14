from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging

from app.database import init_db
from app.redis_client import RedisClient
from app.services.guidelines import load_guidelines
from app.routers import health, chat, ingest, feedback, demo, appointments
from openai import OpenAIError
from anthropic import AnthropicError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Nova Agent...")

    try:
        # Initialize database
        logger.info("Initializing database...")
        await init_db()
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    try:
        # Initialize Redis
        logger.info("Connecting to Redis...")
        redis_client = await RedisClient.get_client()
        if redis_client:
            logger.info("✓ Redis connected")
        else:
            logger.warning("Redis connection failed - continuing without caching")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e} - continuing without caching")

    try:
        logger.info("Loading KB guidelines...")
        guidelines = await load_guidelines()
        if guidelines:
            logger.info("✓ KB guidelines loaded into system prompt")
        else:
            logger.warning("No KB guidelines found — run ingestion with guideline flags")
    except Exception as e:
        logger.warning(f"Failed to load guidelines: {e} — continuing without KB guidelines")

    logger.info("✓ Nova Agent started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Nova Agent...")
    await RedisClient.close()
    logger.info("✓ Nova Agent shut down")


# Create FastAPI app
app = FastAPI(
    title="Nova Agent",
    description="RAG-powered Medical Clinic Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handlers
@app.exception_handler(OpenAIError)
async def openai_exception_handler(request: Request, exc: OpenAIError):
    """Handle OpenAI API errors."""
    logger.error(f"OpenAI API error: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "detail": "OpenAI service temporarily unavailable",
            "error": str(exc)
        }
    )


@app.exception_handler(AnthropicError)
async def anthropic_exception_handler(request: Request, exc: AnthropicError):
    """Handle Anthropic API errors."""
    logger.error(f"Anthropic API error: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Anthropic service temporarily unavailable",
            "error": str(exc)
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc)
        }
    )


# Static files
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(ingest.router, tags=["Ingestion"])
app.include_router(feedback.router, tags=["Feedback"])
app.include_router(demo.router, tags=["Demo"])
app.include_router(appointments.router, tags=["Appointments"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "Nova Agent",
        "version": "1.0.0",
        "description": "RAG-powered Medical Clinic Assistant",
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "ingest": "/ingest",
            "feedback": "/feedback",
            "demo": "/demo",
            "appointments": "/appointments"
        }
    }
