"""Keyword-based detection for common questions that can be answered from config."""

from typing import Optional, Tuple, Dict
from app.config import settings, practitioner_services

# Each topic: list of trigger keywords and a builder that returns context data.
TOPICS: list[dict] = [
    {
        "name": "services",
        "keywords": ["service", "offer", "treatment", "provide"],
    },
    {
        "name": "hours",
        "keywords": ["hour", "open", "close", "when", "schedule"],
    },
    {
        "name": "booking",
        "keywords": ["book", "appointment"],
    },
    {
        "name": "location",
        "keywords": ["location", "address", "contact", "phone", "where"],
    },
    {
        "name": "practitioners",
        "keywords": ["doctor", "practitioner", "staff", "team", "therapist", "who works", "naturopath", "acupuncturist"],
    },
]


def _build_topic_data(topic_name: str) -> Dict:
    """Return structured clinic data for a detected topic."""
    if topic_name == "services":
        return {
            "detail": (
                "We offer the following services: "
                + ", ".join(settings.clinic_services)
                + "."
            ),
            "services": settings.clinic_services,
        }

    if topic_name == "hours":
        return {
            "detail": (
                "Our hours of operation:\n"
                "Monday: 12:00 PM - 8:00 PM\n"
                "Tuesday: 10:00 AM - 8:00 PM\n"
                "Wednesday: 10:00 AM - 6:00 PM\n"
                "Thursday: 10:00 AM - 6:00 PM\n"
                "Friday: 9:00 AM - 6:00 PM\n"
                "Saturday: 9:00 AM - 5:00 PM\n"
                "Sunday: Closed"
            ),
        }

    if topic_name == "location":
        return {
            "detail": (
                "Nova Naturopathic Integrative Clinic is located at "
                "208-6707 Elbow Dr SW, Calgary, AB T2V 0E4. "
                "You can reach us at (587) 391-5753 or email admin@novaclinic.ca. "
                "Free parking is available for up to 2 hours in unreserved yellow stalls "
                "(basement or surface) — just register your license plate."
            ),
        }

    if topic_name == "practitioners":
        lines = []
        for name, info in practitioner_services.items():
            services = ", ".join(info["services"])
            lines.append(f"- {name} ({info['title']}): {services}")
        return {
            "detail": "Our practitioners:\n" + "\n".join(lines),
        }

    # "booking" — no extra data, the router will redirect to booking flow
    return {}


def detect_known_topic(question: str) -> Optional[Tuple[str, Dict]]:
    """
    Check *question* against known topic keywords.

    Returns (topic_name, data_dict) if a match is found, otherwise None.
    """
    q = question.lower()
    for topic in TOPICS:
        if any(kw in q for kw in topic["keywords"]):
            name = topic["name"]
            return name, _build_topic_data(name)
    return None
