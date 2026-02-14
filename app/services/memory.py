import json
import logging
from typing import List, Dict, Optional
import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Redis-backed conversation history per session."""

    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
        self.ttl = settings.conversation_history_ttl
        self.max_history = settings.max_conversation_history

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}:messages"

    def _meta_key(self, session_id: str) -> str:
        return f"session:{session_id}:meta"

    async def get_meta(self, session_id: str) -> Dict:
        """Return session metadata (e.g. patient_type)."""
        if not self.redis:
            return {}
        try:
            raw = await self.redis.get(self._meta_key(session_id))
            return json.loads(raw) if raw else {}
        except Exception as e:
            logger.warning(f"Failed to read session metadata: {e}")
            return {}

    async def set_meta(self, session_id: str, data: Dict) -> None:
        """Merge *data* into session metadata and refresh TTL."""
        if not self.redis:
            return
        try:
            key = self._meta_key(session_id)
            raw = await self.redis.get(key)
            meta = json.loads(raw) if raw else {}
            meta.update(data)
            await self.redis.set(key, json.dumps(meta), ex=self.ttl)
        except Exception as e:
            logger.warning(f"Failed to store session metadata: {e}")

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Return the last N exchanges as [{role, content}, ...]."""
        if not self.redis:
            return []
        try:
            raw = await self.redis.get(self._key(session_id))
            if not raw:
                return []
            messages = json.loads(raw)
            # Return last max_history * 2 items (each exchange = user + assistant)
            limit = self.max_history * 2
            return messages[-limit:]
        except Exception as e:
            logger.warning(f"Failed to read conversation history: {e}")
            return []

    async def add_exchange(
        self, session_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Append a user+assistant exchange and refresh TTL."""
        if not self.redis:
            return
        try:
            key = self._key(session_id)
            raw = await self.redis.get(key)
            messages = json.loads(raw) if raw else []
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})
            # Keep bounded
            limit = self.max_history * 2
            messages = messages[-limit:]
            await self.redis.set(key, json.dumps(messages), ex=self.ttl)
        except Exception as e:
            logger.warning(f"Failed to store conversation history: {e}")
