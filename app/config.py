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
    kb_version: int = 2

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

    # Dashboard
    dashboard_password: str = "nova2026"

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
        "title": "Naturopathic Doctor (ND)",
        "credentials": "BSc (University of Calgary), ND (Canadian College of Naturopathic Medicine)",
        "registrations": "CNDA, CAND, AAND",
        "services": [
            "Naturopathic Medicine",
            "IV Therapy",
            "Injections",
            "Prolotherapy",
            "Functional Testing",
        ],
        "areas_of_focus": "Digestive health, weight management, endocrine, immune support, pain management, nervous system concerns",
        "certifications": "IV nutrient therapy, injection therapies, ozone therapy, regenerative injection therapy",
    },
    "Dr. Marisa Hucal": {
        "title": "Naturopathic Doctor (ND)",
        "credentials": "BSc Honours (University of Calgary), ND (Boucher Institute of Naturopathic Medicine)",
        "registrations": "CNDA, CAND",
        "services": [
            "Naturopathic Medicine",
            "IV Therapy",
            "Injections",
        ],
        "areas_of_focus": "Weight management, digestive health, hormonal health (men and women), stress and mental health",
        "certifications": "Acupuncture, IV therapy, chelation and advanced IV therapies, prescribing upgrade, Metabolic Balance Certified Coach",
    },
    "Dr. Alexa Torontow": {
        "title": "Naturopathic Doctor (ND)",
        "credentials": "BHK (University of British Columbia), ND (Canadian College of Naturopathic Medicine)",
        "registrations": "CNDA, AAND",
        "services": ["Naturopathic Medicine"],
        "areas_of_focus": "Women's hormonal health, fertility, pregnancy, postpartum care, perinatal support",
        "certifications": "Trained Birth Doula",
    },
    "Dr. Madison Thorne": {
        "title": "Naturopathic Doctor (ND)",
        "credentials": "Kinesiology degree, ND (Canadian College of Naturopathic Medicine)",
        "registrations": "CNDA, AAND, CAND, Oncology Association of Naturopathic Doctors",
        "services": [
            "Naturopathic Medicine",
            "IV Therapy",
            "Injections",
        ],
        "areas_of_focus": "Women's hormonal health, general naturopathic medicine",
        "certifications": "Acupuncture, IV therapy, intramuscular injection therapy",
    },
    "Lorena Bulcao": {
        "title": "Dr. Ac, TCMD, RMT",
        "credentials": "Massage Therapy (Mount Royal College), TCMD (Calgary College of Chinese Medicine and Acupuncture)",
        "services": [
            "Acupuncture",
            "Cupping",
            "Facial Rejuvenation",
            "Massage Therapy",
        ],
        "areas_of_focus": "Pain management, musculoskeletal issues, stress management, women's health, facial acupuncture",
        "certifications": "Reiki, reflexology, Thai massage, yoga instruction, Ayurvedic medicine training (India)",
    },
}


def get_practitioners_for_service(service: str) -> list[dict]:
    """Return practitioners who offer a given service."""
    result = []
    for name, info in practitioner_services.items():
        if service in info["services"]:
            result.append({"name": name, "title": info["title"]})
    return result


# ── Delivery mode configuration ───────────────────────────────────────

# Keyed by service_display (consultation sub-option label) first, then
# falls back to the base service name.
SERVICE_DELIVERY_MODES: dict[str, list[str]] = {
    # Consultation sub-options
    "Initial Naturopathic Consultation": ["In-person"],
    "Initial Injection/IV Consultation": ["In-person"],
    "Meet & Greet": ["Phone"],
    # Base services
    "Naturopathic Medicine": ["In-person", "Phone", "Virtual"],
    "Acupuncture": ["In-person"],
    "Massage Therapy": ["In-person"],
}

VIRTUAL_PRACTITIONERS = {"Dr. Alexa Torontow", "Dr. Ali Nurani"}


def get_delivery_modes(service_display: str | None, service: str) -> list[str]:
    """Return available delivery modes for a service.

    Checks the display name (e.g. "Initial Naturopathic Consultation") first,
    then falls back to the base service (e.g. "Naturopathic Medicine").
    Defaults to ["In-person"] if nothing matches.
    """
    if service_display and service_display in SERVICE_DELIVERY_MODES:
        return SERVICE_DELIVERY_MODES[service_display]
    return SERVICE_DELIVERY_MODES.get(service, ["In-person"])


def filter_practitioners_by_delivery_mode(
    practitioners: list[dict], delivery_mode: str
) -> list[dict]:
    """Filter practitioners for Virtual mode (only VIRTUAL_PRACTITIONERS).

    For In-person and Phone, all practitioners are returned unchanged.
    """
    if delivery_mode == "Virtual":
        return [p for p in practitioners if p["name"] in VIRTUAL_PRACTITIONERS]
    return practitioners
