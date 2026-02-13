import openai
from typing import List
import time
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for creating text embeddings using OpenAI."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model
        self.max_retries = 3
        self.base_delay = 1.0

    async def embed_text(self, text: str) -> List[float]:
        """
        Create an embedding for a single text string.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector

        Raises:
            Exception: If embedding fails after retries
        """
        for attempt in range(self.max_retries):
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=text,
                )
                embedding = response.data[0].embedding
                return embedding

            except openai.RateLimitError as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"Rate limit hit, retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"Rate limit exceeded after {self.max_retries} attempts")
                    raise

            except openai.APIError as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"API error, retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"API error after {self.max_retries} attempts: {e}")
                    raise

            except Exception as e:
                logger.error(f"Unexpected error creating embedding: {e}")
                raise

    async def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Create embeddings for multiple texts in batches.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process at once

        Returns:
            List of embedding vectors
        """
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}")

            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                )
                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)

            except Exception as e:
                logger.error(f"Failed to embed batch starting at index {i}: {e}")
                # Fall back to individual embedding for this batch
                for text in batch:
                    embedding = await self.embed_text(text)
                    embeddings.append(embedding)

        return embeddings


# Global instance
embedding_service = EmbeddingService()
