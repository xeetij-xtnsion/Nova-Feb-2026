from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys
    anthropic_api_key: str = ""
    openai_api_key: str

    # LLM Provider: "anthropic" or "openai"
    llm_provider: str = "openai"

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
    similarity_threshold: float = 0.45

    # Cache TTL (seconds)
    retrieval_cache_ttl: int = 3600  # 1 hour
    response_cache_ttl: int = 1800   # 30 minutes

    # OpenAI Settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Anthropic Settings
    claude_model: str = "claude-3-haiku-20240307"
    max_tokens: int = 4096

    # OpenAI LLM Settings
    openai_llm_model: str = "gpt-4o-mini"

    # Conversation Memory
    conversation_history_ttl: int = 3600  # 1 hour
    max_conversation_history: int = 10  # last N exchanges sent to Claude

    # Booking
    booking_state_ttl: int = 1800  # 30 minutes
    clinic_services: list = [
        "Acupuncture",
        "Naturopathic Medicine",
        "Massage Therapy",
        "Initial Consultation",
    ]
    booking_hours_start: int = 9
    booking_hours_end: int = 17
    booking_slot_minutes: int = 60


settings = Settings()

# Practitioner ↔ service mapping
practitioner_services = {
    "Dr. Ali Nurani": {
        "title": "Naturopathic Doctor",
        "services": [
            "Naturopathic Medicine",
            "IV Therapy",
            "Injections",
            "Prolotherapy",
            "Functional Testing",
        ],
    },
    "Dr. Marisa Hucal": {
        "title": "Naturopathic Doctor",
        "services": ["Naturopathic Medicine"],
    },
    "Dr. Chad Patterson": {
        "title": "Naturopathic Doctor",
        "services": ["Naturopathic Medicine", "Pediatric Naturopathic"],
    },
    "Dr. Alexa Torontow": {
        "title": "Naturopathic Doctor",
        "services": ["Naturopathic Medicine"],
    },
    "Lorena Bulcao": {
        "title": "Acupuncturist, TCM Doctor, RMT",
        "services": [
            "Acupuncture",
            "Cupping",
            "Facial Rejuvenation",
            "Massage Therapy",
        ],
    },
}


def get_practitioners_for_service(service: str) -> list[dict]:
    """Return practitioners who offer a given service."""
    result = []
    for name, info in practitioner_services.items():
        if service in info["services"]:
            result.append({"name": name, "title": info["title"]})
    return result
