import redis.asyncio as redis
from typing import Optional
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class RedisClient:
    """Singleton Redis client for caching."""

    _instance: Optional[redis.Redis] = None

    @classmethod
    async def get_client(cls) -> Optional[redis.Redis]:
        """Get or create Redis client instance."""
        if cls._instance is None:
            try:
                cls._instance = redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                # Test connection
                await cls._instance.ping()
                logger.info("Redis connection established")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Continuing without caching.")
                cls._instance = None
        return cls._instance

    @classmethod
    async def close(cls):
        """Close Redis connection."""
        if cls._instance:
            await cls._instance.close()
            cls._instance = None


async def get_redis() -> Optional[redis.Redis]:
    """Dependency for getting Redis client."""
    return await RedisClient.get_client()
