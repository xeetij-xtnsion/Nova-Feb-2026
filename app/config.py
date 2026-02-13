from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys
    anthropic_api_key: str
    openai_api_key: str

    # Database
    database_url: str

    # Redis
    redis_url: str

    # RAG Parameters
    chunk_size: int = 700
    chunk_overlap: int = 120
    top_k: int = 8
    kb_version: int = 1

    # Confidence Thresholds
    similarity_threshold: float = 0.6

    # Cache TTL (seconds)
    retrieval_cache_ttl: int = 3600  # 1 hour
    response_cache_ttl: int = 1800   # 30 minutes

    # OpenAI Settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Anthropic Settings
    claude_model: str = "claude-3-haiku-20240307"
    max_tokens: int = 4096


settings = Settings()
