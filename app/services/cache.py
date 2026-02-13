import hashlib
import json
from typing import Optional, List, Dict, Any
import redis.asyncio as redis
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class CacheService:
    """Two-tier caching service for retrieval and responses."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.retrieval_ttl = settings.retrieval_cache_ttl
        self.response_ttl = settings.response_cache_ttl

    def _embedding_hash(self, embedding: List[float]) -> str:
        """
        Create a hash from an embedding vector.
        Uses first 32 values for efficiency while maintaining uniqueness.

        Args:
            embedding: Embedding vector

        Returns:
            SHA256 hash string
        """
        # Use first 32 floats to create hash (balance between uniqueness and speed)
        sample = embedding[:32]
        # Convert to bytes via JSON serialization
        data = json.dumps(sample).encode('utf-8')
        return hashlib.sha256(data).hexdigest()[:16]  # Use first 16 chars

    def _text_hash(self, text: str) -> str:
        """
        Create a hash from text.

        Args:
            text: Input text

        Returns:
            SHA256 hash string
        """
        data = text.encode('utf-8')
        return hashlib.sha256(data).hexdigest()[:16]  # Use first 16 chars

    async def get_retrieval(
        self,
        embedding: List[float],
        kb_version: int,
        top_k: int
    ) -> Optional[Dict]:
        """
        Get cached retrieval results.

        Args:
            embedding: Query embedding vector
            kb_version: KB version
            top_k: Number of results

        Returns:
            Cached retrieval dictionary or None
        """
        if not self.redis_client:
            return None

        try:
            emb_hash = self._embedding_hash(embedding)
            key = f"retrieval:v{kb_version}:k{top_k}:h{emb_hash}"

            cached = await self.redis_client.get(key)
            if cached:
                logger.info(f"Cache HIT: retrieval ({key})")
                return json.loads(cached)

            logger.debug(f"Cache MISS: retrieval ({key})")
            return None

        except Exception as e:
            logger.warning(f"Error reading retrieval cache: {e}")
            return None

    async def set_retrieval(
        self,
        embedding: List[float],
        kb_version: int,
        top_k: int,
        data: Dict
    ):
        """
        Cache retrieval results.

        Args:
            embedding: Query embedding vector
            kb_version: KB version
            top_k: Number of results
            data: Retrieval results to cache
        """
        if not self.redis_client:
            return

        try:
            emb_hash = self._embedding_hash(embedding)
            key = f"retrieval:v{kb_version}:k{top_k}:h{emb_hash}"

            await self.redis_client.setex(
                key,
                self.retrieval_ttl,
                json.dumps(data)
            )
            logger.debug(f"Cached retrieval: {key}")

        except Exception as e:
            logger.warning(f"Error writing retrieval cache: {e}")

    async def get_response(
        self,
        question: str,
        kb_version: int
    ) -> Optional[Dict]:
        """
        Get cached response.

        Args:
            question: User question
            kb_version: KB version

        Returns:
            Cached response dictionary or None
        """
        if not self.redis_client:
            return None

        try:
            text_hash = self._text_hash(question)
            key = f"response:v{kb_version}:h{text_hash}"

            cached = await self.redis_client.get(key)
            if cached:
                logger.info(f"Cache HIT: response ({key})")
                return json.loads(cached)

            logger.debug(f"Cache MISS: response ({key})")
            return None

        except Exception as e:
            logger.warning(f"Error reading response cache: {e}")
            return None

    async def set_response(
        self,
        question: str,
        kb_version: int,
        data: Dict
    ):
        """
        Cache response.

        Args:
            question: User question
            kb_version: KB version
            data: Response data to cache
        """
        if not self.redis_client:
            return

        try:
            text_hash = self._text_hash(question)
            key = f"response:v{kb_version}:h{text_hash}"

            await self.redis_client.setex(
                key,
                self.response_ttl,
                json.dumps(data)
            )
            logger.debug(f"Cached response: {key}")

        except Exception as e:
            logger.warning(f"Error writing response cache: {e}")


def get_cache_service(redis_client: Optional[redis.Redis] = None) -> CacheService:
    """
    Get cache service instance.

    Args:
        redis_client: Redis client (optional)

    Returns:
        CacheService instance
    """
    return CacheService(redis_client)
