"""Keyword-based detection for common questions that can be answered from config."""

from typing import Optional, Tuple, Dict
from app.config import settings, practitioner_services
from app.services.nlp_utils import word_match

# Each topic: list of trigger keywords/phrases and a builder that returns context data.
# "phrases" = multi-word, safe for substring matching
# "words"   = short words, need word-boundary matching to avoid false positives
TOPICS: list[dict] = [
    # More specific multi-word topics first to avoid false matches
    {
        "name": "what_to_bring",
        "phrases": ["what to bring", "bring with me", "what do i need", "need to bring",
                     "should i bring", "prepare for my", "how to prepare",
                     "first visit prepare", "what should i bring"],
    },
    {
        "name": "consultations",
        "phrases": ["meet and greet", "meet & greet", "initial consultation",
                     "initial visit", "first visit", "free consultation",
                     "free meet", "consultation option", "consultation type"],
    },
    {
        "name": "services",
        "phrases": ["what do you do", "what do you offer", "what services",
                     "services do you", "treatments do you", "do you provide"],
        "words": ["service", "treatment"],
    },
    {
        "name": "hours",
        "phrases": ["what hours", "your hours", "hours of operation", "business hours",
                     "opening hours", "are you open", "when are you open",
                     "when do you open", "when do you close", "what time do you"],
        "words": ["hours"],
    },
    {
        "name": "booking",
        "phrases": ["make an appointment"],
        "words": ["book", "booking", "appointment"],
    },
    {
        "name": "location",
        "phrases": ["where are you", "where is the clinic", "where is it located",
                     "how to get there", "how do i get to", "contact info",
                     "contact number", "phone number", "call you",
                     "your address", "clinic address", "get directions"],
        "words": ["location", "address", "parking", "directions"],
    },
    {
        "name": "practitioners",
        "phrases": ["who works", "who are the", "your doctors", "your team",
                     "who are your", "meet the team", "which doctors"],
        "words": ["doctor", "practitioner", "therapist", "naturopath", "acupuncturist"],
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

    if topic_name == "consultations":
        return {
            "detail": (
                "Nova Clinic offers three consultation options for new patients:\n"
                "1. Initial Naturopathic Consultation — ~80 minutes, $295. "
                "A comprehensive assessment with one of our naturopathic doctors.\n"
                "2. Initial Injection/IV Consultation — ~80 minutes, from $290. "
                "For patients interested in injection or IV nutrient therapy.\n"
                "3. Meet & Greet — FREE, 15 minutes (phone only). "
                "A no-obligation introductory call with a naturopathic doctor "
                "to discuss your health concerns and see if we're a good fit.\n\n"
                "Yes, we do offer a free Meet & Greet! It's a great way to get started."
            ),
        }

    if topic_name == "what_to_bring":
        return {
            "detail": (
                "What to bring to your appointment at Nova Clinic:\n"
                "- A valid government-issued photo ID (driver's license, passport, etc.)\n"
                "- Your insurance card or extended health benefits information, if applicable\n"
                "- A list of any current medications or supplements you're taking\n"
                "- Any relevant medical records, lab results, or referral letters\n"
                "- Comfortable clothing (especially for massage, acupuncture, or osteopathic treatments)\n"
                "- For new patients: please arrive 10-15 minutes early to complete intake forms\n\n"
                "We'll take care of everything else at the clinic!"
            ),
        }

    # "booking" — no extra data, the router will redirect to booking flow
    return {}


def detect_known_topic(question: str) -> Optional[Tuple[str, Dict]]:
    """
    Check *question* against known topic keywords.

    Uses phrase (substring) matching for multi-word phrases and
    word-boundary matching for short single words to avoid false positives.

    Returns (topic_name, data_dict) if a match is found, otherwise None.
    """
    q = question.lower()
    for topic in TOPICS:
        # Multi-word phrases: safe as substring match
        phrases = topic.get("phrases", [])
        if any(phrase in q for phrase in phrases):
            name = topic["name"]
            return name, _build_topic_data(name)
        # Short words: require word-boundary match
        words = topic.get("words", [])
        if any(word_match(w, q) for w in words):
            name = topic["name"]
            return name, _build_topic_data(name)
    return None
