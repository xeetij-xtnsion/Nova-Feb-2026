from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from typing import Optional, List, Dict
import asyncio
import uuid
import json
import logging
import re
import time

from app.schemas.chat import ChatRequest, ChatResponse, Action
from app.database import get_db, AsyncSessionLocal
from app.redis_client import get_redis
from app.models.analytics import ChatAnalytics
from app.services.embedding import embedding_service
from app.services.retrieval import retrieve_with_confidence
from app.services.llm import llm_service
from app.services.cache import get_cache_service
from app.services.memory import ConversationMemory
from app.services.booking import BookingService, SERVICE_KEYWORDS, CONSULT_KEYWORDS, CONFUSION_PHRASES, CONSULTATION_OPTIONS
from app.services.known_topics import detect_known_topic
from app.services.patient_profiles import lookup_patient_by_phone, is_valid_phone_input
from app.services.llm import PHONE_PROMPT_TEXT, PHONE_NO_MATCH_TEXT, PHONE_INVALID_TEXT
from app.services.nlp_utils import word_match, any_word_match
from app.config import settings, practitioner_services

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Analytics helper ──────────────────────────────────────────────

async def _record_analytics(
    *,
    session_id: str,
    question: str,
    answer: str,
    response_source: str,
    route_taken: str,
    confidence: str,
    is_knowledge_gap: bool = False,
    max_similarity: Optional[float] = None,
    chunk_count: int = 0,
    patient_type: Optional[str] = None,
    response_time_ms: Optional[int] = None,
) -> None:
    """Fire-and-forget: write one analytics row using its own DB session."""
    try:
        sentiment = await llm_service.analyze_sentiment(question)
        async with AsyncSessionLocal() as session:
            row = ChatAnalytics(
                session_id=session_id,
                question=question[:2000],
                answer=answer[:2000],
                response_source=response_source,
                route_taken=route_taken,
                confidence=confidence,
                is_knowledge_gap=is_knowledge_gap,
                max_similarity=max_similarity,
                chunk_count=chunk_count,
                patient_type=patient_type,
                sentiment=sentiment,
                response_time_ms=response_time_ms,
            )
            session.add(row)
            await session.commit()
    except Exception as e:
        logger.warning(f"Analytics write failed: {e}")


# ── Patient type detection ────────────────────────────────────────

NEW_PATIENT_KEYWORDS = ["new patient", "first time", "first visit", "never been", "i'm new", "im new here"]
RETURNING_PATIENT_KEYWORDS = [
    "returning patient", "i'm returning", "im returning", "been here before",
    "came before", "i need a follow-up", "book a follow-up", "book follow-up",
    "been before", "visited before", "i've been here", "ive been here",
]

# Negation prefixes that invalidate patient type detection
_PATIENT_TYPE_NEGATIONS = ["not a ", "not the ", "never ", "don't ", "dont "]


def _detect_patient_type(message: str) -> Optional[str]:
    """Return 'new' or 'returning' if the message indicates patient type."""
    msg = message.lower()
    # Check negation: "I'm not a new patient" should not classify as "new"
    if any(neg + "new" in msg for neg in _PATIENT_TYPE_NEGATIONS):
        return "returning"  # "not new" implies returning
    if any(neg + "returning" in msg for neg in _PATIENT_TYPE_NEGATIONS):
        return "new"  # "not returning" implies new
    if any(kw in msg for kw in NEW_PATIENT_KEYWORDS):
        return "new"
    if any(kw in msg for kw in RETURNING_PATIENT_KEYWORDS):
        return "returning"
    return None


def _infer_service_from_history(history: List[Dict[str, str]]) -> Optional[str]:
    """Check recent conversation for service mentions to carry context into booking.

    Prefers user messages (stronger intent signal). For assistant messages,
    only infers if exactly one service is mentioned (skip listings).
    """
    if not history:
        return None
    recent = history[-4:]

    # Pass 1: check user messages (most reliable)
    for msg in reversed(recent):
        if msg.get("role") != "user":
            continue
        text = msg.get("content", "").lower()
        for keyword, service in SERVICE_KEYWORDS.items():
            if word_match(keyword, text):
                return service

    # Pass 2: check assistant messages (skip if multiple services mentioned)
    for msg in reversed(recent):
        if msg.get("role") != "assistant":
            continue
        text = msg.get("content", "").lower()
        matches = [svc for kw, svc in SERVICE_KEYWORDS.items() if word_match(kw, text)]
        if len(matches) == 1:
            return matches[0]

    return None


# Specific consultation terms that are distinctive enough to infer intent from history
# (avoids generic "consult" which appears in most bot responses)
_CONSULT_INFERENCE_KEYWORDS = [
    "meet and greet", "meet & greet",
    "initial naturopathic", "initial injection", "initial iv",
    "initial consultation", "schedule an initial",
]


def _infer_consultation_from_history(history: List[Dict[str, str]]) -> bool:
    """Check recent conversation for consultation-specific mentions."""
    if not history:
        return False
    recent = history[-4:]
    for msg in reversed(recent):
        text = msg.get("content", "").lower()
        if any(kw in text for kw in _CONSULT_INFERENCE_KEYWORDS):
            return True
    return False


# ── Contextual booking intent (user affirming a bot's booking offer) ──

_BOOKING_OFFER_PHRASES = [
    "would you like to book", "would you like me to book",
    "would you like me to check", "would you like to schedule",
    "shall i book", "help you book", "want to book",
    "like to book", "ready to book", "want me to book",
    "book that appointment", "set that up",
    "like to proceed", "would you like to proceed",
    "want to proceed", "shall we proceed",
]

_AFFIRMATIVE_WORDS = {
    "yes", "yeah", "yep", "yea", "sure", "ok", "okay",
    "absolutely", "definitely",
}
# Note: "please" removed — too broad ("please tell me about..." is not an affirmation)

_AFFIRMATIVE_PHRASES = [
    "let's do it", "lets do it", "go ahead", "sounds good",
    "let's go", "lets go", "yes please", "i'd like that",
    "i would like that", "that would be great", "of course",
]


def _is_contextual_booking_intent(message: str, history: List[Dict[str, str]]) -> bool:
    """Check if the user is affirming a booking offer from the bot's last message."""
    if not history:
        return False
    msg = message.strip().lower()
    # Reject if the message expresses uncertainty or negation
    # (e.g. "not sure" contains "sure" but is NOT an affirmation)
    _NEGATION_PREFIXES = [
        "not sure", "not really", "i'm not", "im not", "i am not",
        "don't", "dont", "do not", "no ", "nah", "nope",
        "not yet", "not right now", "maybe not",
    ]
    if any(neg in msg for neg in _NEGATION_PREFIXES):
        return False
    if any(phrase in msg for phrase in CONFUSION_PHRASES):
        return False
    # Check if user's response is affirmative
    msg_words = set(msg.split())
    is_affirm = bool(msg_words & _AFFIRMATIVE_WORDS) or any(
        p in msg for p in _AFFIRMATIVE_PHRASES
    )
    if not is_affirm:
        return False
    # If the message is long and contains qualifiers, the user wants something
    # else first ("yes but tell me about pricing first") — don't trigger booking
    _QUALIFIERS = ["but", "however", "first", "before", "tell me", "what about", "actually"]
    if len(msg_words) > 4 and any(q in msg for q in _QUALIFIERS):
        return False
    # Check if bot's last message offered booking
    for m in reversed(history):
        if m.get("role") == "assistant":
            bot_msg = m.get("content", "").lower()
            return any(phrase in bot_msg for phrase in _BOOKING_OFFER_PHRASES)
    return False


_UPCOMING_KEYWORDS = [
    "upcoming", "next visit", "next appointment", "my visit",
    "my appointment", "when is my", "details of my",
]


def _is_upcoming_appointment_query(message: str) -> bool:
    """Return True if the message is asking about an existing upcoming appointment."""
    msg = message.lower()
    return any(kw in msg for kw in _UPCOMING_KEYWORDS)


def _build_verified_patient_actions(patient: dict) -> List[Action]:
    """Return action buttons for a verified returning patient."""
    actions: List[Action] = []
    if patient.get("upcoming_appointment"):
        actions.append(Action(
            label="View Upcoming Appointment",
            value=f"What are the details of my upcoming visit on {patient['upcoming_appointment']}?",
            action_type="quick_reply",
        ))
    actions.append(Action(
        label="Book Follow-up",
        value="I'd like to book an appointment",
        action_type="booking",
    ))
    actions.append(Action(
        label="Our Services",
        value="What services do you offer?",
        action_type="quick_reply",
    ))
    return actions


# ── Contextual action helpers ─────────────────────────────────────

EMERGENCY_KEYWORDS = [
    "emergency", "heart attack", "call 911", "call 9-1-1",
    "seek immediate", "immediate medical", "paralyz", "paralys",
    "stroke", "chest pain", "can't breathe", "cannot breathe", "cant breathe",
    "difficulty breathing", "trouble breathing",
    "severe bleeding", "unconscious", "suicide", "overdose",
    "allergic reaction", "anaphylaxis", "seizure",
]

# ── Broad topic actions (matched on QUESTION only) ────────────────

# Each entry: (phrases, words, actions)
# "phrases" = multi-word, safe for substring matching
# "words"   = short, need word-boundary matching
_BROAD_TOPIC_ACTIONS: List[tuple] = [
    (["what do you do", "what do you offer", "what services"], ["service", "treatment"],
     [
        Action(label="Naturopathic Medicine", value="Tell me about Naturopathic Medicine", action_type="quick_reply"),
        Action(label="Acupuncture", value="Tell me about Acupuncture", action_type="quick_reply"),
        Action(label="Massage Therapy", value="Tell me about Massage Therapy", action_type="quick_reply"),
        Action(label="IV Therapy", value="Tell me about IV Nutrient Therapy", action_type="quick_reply"),
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
    ]),
    (["your hours", "hours of operation", "when are you open", "when do you open",
      "when do you close", "are you open", "what time do you"], ["hours"],
     [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
        Action(label="Our Location", value="Where is the clinic located?", action_type="quick_reply"),
    ]),
    (["how much", "what does it cost"], ["cost", "price", "fee", "pricing", "insurance"],
     [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
    ]),
    (["where are you", "where is the clinic", "how to get there", "find you",
      "your address", "clinic address"], ["location", "address", "parking", "directions"],
     [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Hours", value="What are your hours of operation?", action_type="quick_reply"),
    ]),
    (["who works", "your doctors", "your team", "which doctors", "who are the"],
     ["doctor", "practitioner", "therapist"],
     [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
    ]),
]

# ── Service-specific sub-actions (matched on question + answer) ───

_BACK_BTN = Action(label="\u2190 Back", value="What services do you offer?", action_type="back")

# Each entry: (phrases, words, actions)
_SERVICE_ACTIONS: List[tuple] = [
    # Massage Therapy — show duration options
    ([], ["massage"],
     [
        Action(label="30 min — $75", value="Tell me about a 30-minute massage", action_type="quick_reply"),
        Action(label="60 min — $120", value="Tell me about a 60-minute massage", action_type="quick_reply"),
        Action(label="90 min — $160", value="Tell me about a 90-minute massage", action_type="quick_reply"),
        Action(label="Book Massage", value="I'd like to book a massage appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Acupuncture — show types
    ([], ["acupuncture"],
     [
        Action(label="Classic Acupuncture", value="Tell me about classic acupuncture sessions", action_type="quick_reply"),
        Action(label="Body Cupping — $70", value="Tell me about body cupping therapy", action_type="quick_reply"),
        Action(label="Facial Rejuvenation", value="Tell me about facial rejuvenation acupuncture", action_type="quick_reply"),
        Action(label="Book Acupuncture", value="I'd like to book an acupuncture appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Cupping
    ([], ["cupping"],
     [
        Action(label="Body Cupping — $70", value="What does body cupping involve and how much does it cost?", action_type="quick_reply"),
        Action(label="Acupuncture + Cupping", value="Can I combine acupuncture with cupping?", action_type="quick_reply"),
        Action(label="Book Cupping", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Facial Rejuvenation
    (["facial rejuvenation", "facial acupuncture"], [],
     [
        Action(label="Rejuvenating Facial", value="Tell me about rejuvenating facial acupuncture and pricing", action_type="quick_reply"),
        Action(label="Non-Needle Facial — $80", value="Tell me about the non-needle facial acupuncture option", action_type="quick_reply"),
        Action(label="Book Facial", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Naturopathic Medicine
    ([], ["naturopath", "naturopathic"],
     [
        Action(label="Initial Visit — $295", value="What happens at an initial naturopathic consultation?", action_type="quick_reply"),
        Action(label="Follow-Up Options", value="What are the follow-up appointment options and pricing for naturopathic visits?", action_type="quick_reply"),
        Action(label="Free Meet & Greet", value="Do you offer a free meet and greet with a naturopathic doctor?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an initial consultation", action_type="booking"),
        _BACK_BTN,
    ]),
    # IV Therapy
    (["iv therapy", "iv nutrient", "iv drip", "iv treatment", "intravenous"], [],
     [
        Action(label="IV Drip Options", value="What IV drip options do you offer and what are the prices?", action_type="quick_reply"),
        Action(label="IV Push Options", value="Tell me about IV push treatments", action_type="quick_reply"),
        Action(label="Initial IV Consult", value="What's involved in the initial IV therapy consultation?", action_type="quick_reply"),
        Action(label="Book IV Consult", value="I'd like to book an initial consultation", action_type="booking"),
        _BACK_BTN,
    ]),
    # Injections
    ([], ["injection", "injections"],
     [
        Action(label="Vitamin IM Shot", value="Tell me about vitamin intramuscular injections and pricing", action_type="quick_reply"),
        Action(label="Trigger Point — $150+", value="Tell me about trigger point injection therapy", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an initial consultation", action_type="booking"),
        _BACK_BTN,
    ]),
    # Prolotherapy
    (["prolotherap"], [],
     [
        Action(label="How it works", value="How does prolotherapy work and what conditions does it treat?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an initial consultation", action_type="booking"),
        _BACK_BTN,
    ]),
    # Functional Testing
    (["functional test", "lab test", "hormone test", "food sensitiv", "functional testing",
      "lab testing", "diagnostic testing"], [],
     [
        Action(label="Types of Tests", value="What types of functional tests do you offer?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an initial consultation", action_type="booking"),
        _BACK_BTN,
    ]),
    # Pediatric — use word-boundary for "kid" to avoid matching "kidney"
    (["pediatric"], ["child", "children", "kids", "infant", "baby", "toddler"],
     [
        Action(label="Pediatric Naturopathic", value="Tell me about pediatric naturopathic medicine", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an initial consultation", action_type="booking"),
        _BACK_BTN,
    ]),
]

# ── Symptom/condition → service suggestions ───────────────────────

# Each entry: (phrases, words, info_actions_only)
# Booking CTA + Back button are added dynamically by _build_symptom_actions
_SYMPTOM_ACTIONS: List[tuple] = [
    (["back pain", "neck pain", "back is hurting", "back hurts", "neck hurts",
      "my back", "my neck", "lower back", "upper back"],
     ["pain", "painful", "sore", "soreness", "muscle", "tension", "headache",
      "migraine", "stiff", "stiffness", "hurt", "hurting", "hurts", "ache",
      "aching", "aches", "injury", "injured", "spasm"],
     [
        Action(label="Acupuncture for Pain", value="Can acupuncture help with pain relief?", action_type="quick_reply"),
        Action(label="Massage for Pain", value="Tell me about massage therapy for pain", action_type="quick_reply"),
        Action(label="Trigger Point Injections", value="Tell me about trigger point injection therapy", action_type="quick_reply"),
    ]),
    (["mental health", "can't sleep", "cant sleep", "trouble sleeping"],
     ["stress", "anxiety", "anxious", "relax", "relaxation", "sleep",
      "insomnia", "burnout", "overwhelmed", "depressed", "depression"],
     [
        Action(label="Acupuncture for Stress", value="Can acupuncture help with stress and anxiety?", action_type="quick_reply"),
        Action(label="Massage for Relaxation", value="Tell me about massage for relaxation", action_type="quick_reply"),
        Action(label="Naturopathic Support", value="How can naturopathic medicine help with stress?", action_type="quick_reply"),
    ]),
    (["digestive issue", "stomach issue", "gut issue", "tummy trouble", "gut health"],
     ["digest", "digestion", "gut", "bloat", "bloating", "ibs", "stomach",
      "nausea", "constipat", "sibo"],
     [
        Action(label="Naturopathic Assessment", value="Gut health is a focus of all our naturopathic doctors. How can they help with digestive issues?", action_type="quick_reply"),
        Action(label="GI-360 Gut Testing", value="Tell me about the GI-360 comprehensive gut test", action_type="quick_reply"),
        Action(label="SIBO Breath Test", value="Tell me about SIBO breath testing", action_type="quick_reply"),
    ]),
    (["trying to conceive", "trouble conceiving", "want to get pregnant",
      "fertility treatment", "fertility support"],
     ["fertil", "fertility", "conceiv", "infertil", "ivf", "iui"],
     [
        Action(label="Dr. Alexa Torontow", value="I'd like to book a consultation with Dr. Alexa Torontow for fertility support", action_type="quick_reply"),
        Action(label="Dr. Marisa Hucal", value="I'd like to book a consultation with Dr. Marisa Hucal for fertility support", action_type="quick_reply"),
        Action(label="Learn More", value="How can naturopathic medicine help with fertility?", action_type="quick_reply"),
    ]),
    (["low energy", "no energy", "always tired"],
     ["hormone", "hormonal", "thyroid", "fatigue", "energy", "tired",
      "exhausted", "menopaus", "period", "pcos"],
     [
        Action(label="Naturopathic Assessment", value="How can naturopathic medicine help with hormonal issues?", action_type="quick_reply"),
        Action(label="DUTCH Hormone Test", value="Tell me about the DUTCH hormone test", action_type="quick_reply"),
    ]),
    (["anti-aging", "skin issue", "skin problem", "skin condition"],
     ["skin", "acne", "eczema", "psoriasis", "rash", "wrinkle", "aging"],
     [
        Action(label="Facial Rejuvenation", value="Tell me about facial rejuvenation acupuncture", action_type="quick_reply"),
        Action(label="Naturopathic Assessment", value="How can naturopathic medicine help with skin conditions?", action_type="quick_reply"),
    ]),
    (["immune support", "immune system", "keep getting sick", "getting sick often"],
     ["flu", "vitamin", "boost", "immunity", "wellness", "detox"],
     [
        Action(label="IV Nutrient Therapy", value="Tell me about IV nutrient therapy for immune support", action_type="quick_reply"),
        Action(label="Vitamin Injections", value="Tell me about vitamin intramuscular injections", action_type="quick_reply"),
        Action(label="Naturopathic Support", value="How can naturopathic medicine support immunity?", action_type="quick_reply"),
    ]),
    (["sport injury", "sports injury", "joint pain", "joint issue"],
     ["joint", "ligament", "tendon", "knee", "shoulder", "elbow", "ankle", "sprain"],
     [
        Action(label="Prolotherapy", value="How does prolotherapy work for joint issues?", action_type="quick_reply"),
        Action(label="Acupuncture for Joints", value="Can acupuncture help with joint pain?", action_type="quick_reply"),
    ]),
    (["food allergy", "food sensitivity", "food intolerance", "food reaction",
      "weight loss", "lose weight", "gain weight"],
     ["weight", "diet", "nutrition", "allerg", "intolerance", "histamine"],
     [
        Action(label="Naturopathic Assessment", value="How can naturopathic medicine help with weight and nutrition?", action_type="quick_reply"),
        Action(label="Food Sensitivity Testing", value="Do you offer food sensitivity testing?", action_type="quick_reply"),
        Action(label="Food Reactions Info", value="What is the difference between food allergies, sensitivities, and intolerances?", action_type="quick_reply"),
    ]),
    (["mold exposure", "toxin exposure"],
     ["mold", "toxin", "environmental"],
     [
        Action(label="Mold Testing", value="Tell me about the MycoTOX mold testing", action_type="quick_reply"),
        Action(label="Environmental Toxin Test", value="Tell me about the GPL-Tox environmental toxin test", action_type="quick_reply"),
        Action(label="Naturopathic Assessment", value="How can naturopathic medicine help with toxin exposure?", action_type="quick_reply"),
    ]),
    (["cancer treatment", "cancer support", "cancer care", "cancer nutrition",
      "going through cancer", "diagnosed with cancer"],
     ["cancer", "oncology", "tumor", "tumour", "chemo", "chemotherapy",
      "radiation", "carcinoma", "lymphoma", "leukemia"],
     [
        Action(label="Consult Dr. Nurani", value="I'd like to book an initial consultation with Dr. Nurani for cancer co-management support", action_type="quick_reply"),
        Action(label="IV Nutrition Therapy", value="Tell me about cancer-focused IV nutrition therapies", action_type="quick_reply"),
        Action(label="Learn More", value="How can naturopathic medicine support cancer care?", action_type="quick_reply"),
    ]),
    (["autoimmune condition", "autoimmune disease", "autoimmune disorder",
      "immune disorder", "immune condition", "immune disease"],
     ["autoimmune", "lupus", "rheumatoid", "celiac", "gluten",
      "hashimoto", "graves", "crohn", "colitis", "scleroderma",
      "sjogren", "fibromyalgia", "psoriatic arthritis", "ankylosing",
      "multiple sclerosis", "myasthenia", "guillain", "vitiligo",
      "alopecia areata", "pemphigus", "vasculitis", "addison",
      "uveitis", "sarcoidosis", "polymyalgia"],
     [
        Action(label="Consult Dr. Nurani", value="I'd like to book an initial consultation with Dr. Nurani for autoimmune support", action_type="quick_reply"),
        Action(label="Autoimmunity Screen", value="Tell me about the Antibody Array 5 autoimmunity test", action_type="quick_reply"),
        Action(label="Learn More", value="What autoimmune conditions does Dr. Nurani treat?", action_type="quick_reply"),
    ]),
]

# ── Practitioner names for detection ──────────────────────────────

_PRACTITIONER_KEYWORDS = {
    "ali": "Dr. Ali Nurani",
    "nurani": "Dr. Ali Nurani",
    "marisa": "Dr. Marisa Hucal",
    "hucal": "Dr. Marisa Hucal",
    "alexa": "Dr. Alexa Torontow",
    "torontow": "Dr. Alexa Torontow",
    "madison": "Dr. Madison Thorne",
    "thorne": "Dr. Madison Thorne",
    "lorena": "Lorena Bulcao",
    "bulcao": "Lorena Bulcao",
}
# Note: practitioner matching uses word_match() to avoid "ali" matching
# inside "specialist", "vitality", etc. See priority 6 in _generate_contextual_actions.

# Words that suggest the user is asking about a specific person
_PERSON_INDICATORS = (
    "dr ", "dr. ", "doctor ", "does ", "is ",
    "who is ", "about ", "meet ", "see ",
)

_PERSON_QUESTION_WORDS = ("work", "qualification", "credential", "available",
                          "specialize", "experience", "background", "offer")


def _extract_unknown_practitioner(question: str) -> Optional[str]:
    """If the question asks about a person not on our team, return the mentioned name.

    Returns the extracted name string (e.g. "Dr. Aisha") or None.
    """
    q = question.lower().strip()

    # Must look like a person-related question
    has_person_indicator = any(ind in q for ind in _PERSON_INDICATORS)
    has_person_question = any(word_match(w, q) for w in _PERSON_QUESTION_WORDS)
    if not (has_person_indicator or has_person_question):
        return None

    # Check it's NOT about a known practitioner
    for keyword in _PRACTITIONER_KEYWORDS:
        if word_match(keyword, q):
            return None

    # Heuristic: contains "dr"/"doctor" + a name
    if any(ind in q for ind in ("dr ", "dr. ", "doctor ")):
        # Extract the name after dr/doctor, stopping at common non-name words
        _STOP_WORDS = {
            "there", "here", "work", "works", "working", "available", "in",
            "on", "at", "is", "are", "do", "does", "have", "has", "the",
            "today", "tomorrow", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "this", "next", "still",
        }
        m = re.search(r'(?:dr\.?\s+|doctor\s+)(\w+)', q)
        if m:
            name_parts = [m.group(1)]
            # Try to grab a second word (last name) if it's not a stop word
            rest = q[m.end():].strip()
            m2 = re.match(r'(\w+)', rest)
            if m2 and m2.group(1) not in _STOP_WORDS:
                name_parts.append(m2.group(1))
            return "Dr. " + " ".join(w.title() for w in name_parts)
        return "that practitioner"

    return None


def _smart_booking_action(patient_type: Optional[str] = None) -> Action:
    """Return a booking action with label appropriate to patient type."""
    if patient_type == "new":
        return Action(label="Book Initial Consultation", value="I'd like to book an initial consultation", action_type="booking")
    if patient_type == "returning":
        return Action(label="Book Follow-up", value="I'd like to book an appointment", action_type="booking")
    return Action(label="Book Consultation", value="I'd like to book an initial consultation", action_type="booking")


_NEW_PATIENT_SYMPTOM_ACTIONS = [
    Action(label="Book Initial Consultation", value="I'd like to book an initial consultation", action_type="booking"),
    Action(label="Free Meet & Greet", value="Do you offer a free meet and greet with a naturopathic doctor?", action_type="quick_reply"),
    Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
]


def _build_symptom_actions(
    info_actions: List[Action], patient_type: Optional[str] = None
) -> List[Action]:
    """Build the full action list for a symptom match.

    New patients get consultation entry points (Initial Consultation,
    Meet & Greet) since they need an assessment before choosing a service.
    Returning patients get service-specific drill-down buttons.
    """
    if patient_type == "new":
        return _NEW_PATIENT_SYMPTOM_ACTIONS
    return [_smart_booking_action(patient_type)] + info_actions + [_BACK_BTN]


def _generate_contextual_actions(
    question: str, answer: str, patient_type: Optional[str] = None,
    recently_booked: bool = False,
) -> List[Action]:
    """Return relevant action buttons based on context.

    Priority order:
      0. Emergency → suppress all actions
      0b. Recently booked → helpful post-booking actions (no booking CTAs)
      1. Broad topics (question only) — general info questions
      2. Symptoms in QUESTION → consultation-first actions (takes priority
         over service mentions that may appear in the LLM answer)
      3. Services in QUESTION → service sub-actions
      4. Services in ANSWER (fallback) → service sub-actions
      5. Symptoms in ANSWER (fallback)
      6. Practitioner mention
      7. Patient-type fallback
      8. Generic fallback
    """
    q_lower = question.lower()
    a_lower = answer.lower()

    # 0. Suppress actions for emergency responses
    if any(kw in (q_lower + " " + a_lower) for kw in EMERGENCY_KEYWORDS):
        return []

    # 0b. After a completed booking, show helpful actions — no more booking CTAs
    if recently_booked:
        return [
            Action(label="What to Bring", value="What should I bring to my appointment?", action_type="quick_reply"),
            Action(label="Our Hours", value="What are your hours of operation?", action_type="quick_reply"),
            Action(label="Our Location", value="Where is the clinic located?", action_type="quick_reply"),
        ]

    # 0c. Consultation context → show consultation-relevant actions
    _CONSULT_CONTEXT_KW = [
        "meet and greet", "meet & greet",
        "initial consultation", "initial naturopathic",
        "initial injection", "initial iv",
        "first time", "first visit", "first appointment",
    ]
    if any(kw in q_lower for kw in _CONSULT_CONTEXT_KW):
        return [
            Action(label="Book Meet & Greet", value="I'd like to book a meet and greet", action_type="booking"),
            Action(label="Book Initial Consultation", value="I'd like to book an initial consultation", action_type="booking"),
            Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
        ]

    # 1. Broad topics — match on QUESTION only to avoid false positives
    for phrases, words, actions in _BROAD_TOPIC_ACTIONS:
        if any(p in q_lower for p in phrases) or any_word_match(words, q_lower):
            return actions

    # 2. Symptoms in QUESTION → consultation-first actions
    for phrases, words, info_actions in _SYMPTOM_ACTIONS:
        if any(p in q_lower for p in phrases) or any_word_match(words, q_lower):
            return _build_symptom_actions(info_actions, patient_type)

    # 3. Services in QUESTION → service sub-actions
    for phrases, words, actions in _SERVICE_ACTIONS:
        if any(p in q_lower for p in phrases) or any_word_match(words, q_lower):
            return actions

    # 4. Services in ANSWER (fallback — the LLM mentioned a service)
    # If the answer mentions MULTIPLE services, show generic service list
    # instead of the first match (avoids massage buttons when LLM lists several options)
    answer_service_matches = []
    for i, (phrases, words, actions) in enumerate(_SERVICE_ACTIONS):
        if any(p in a_lower for p in phrases) or any_word_match(words, a_lower):
            answer_service_matches.append((i, actions))
    if len(answer_service_matches) == 1:
        return answer_service_matches[0][1]
    elif len(answer_service_matches) > 1:
        # Multiple services mentioned → show general service list with booking
        return [
            Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
            _smart_booking_action(patient_type),
        ]

    # 5. Symptoms in ANSWER (fallback — the LLM discussed symptoms)
    for phrases, words, info_actions in _SYMPTOM_ACTIONS:
        if any(p in a_lower for p in phrases) or any_word_match(words, a_lower):
            return _build_symptom_actions(info_actions, patient_type)

    # 6. Practitioner mention → offer to book with them (word-boundary matching)
    combined = q_lower + " " + a_lower
    for keyword, name in _PRACTITIONER_KEYWORDS.items():
        if word_match(keyword, combined):
            return [
                Action(label=f"Book with {name.split()[0]} {name.split()[-1]}", value=f"I'd like to book with {name}", action_type="booking"),
                Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
            ]

    # 7. Patient-type-aware fallback
    if patient_type == "new":
        return [
            Action(label="Book Initial Consultation", value="I'd like to book an appointment", action_type="booking"),
            Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
        ]
    if patient_type == "returning":
        return [
            Action(label="Book Follow-up", value="I'd like to book an appointment", action_type="booking"),
            Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
        ]

    # 8. Generic fallback
    return [
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
        _smart_booking_action(patient_type),
    ]


# ── Side question detection during booking ────────────────────────

_QUESTION_STARTERS = (
    "what ", "how ", "where ", "when ", "who ", "why ", "which ",
    "does ", "do you ", "is ", "are ", "can ", "will ", "could ",
    "tell me", "explain", "describe",
)


# ── Booking handler ───────────────────────────────────────────────

async def _handle_booking_step(
    session_id: str,
    message: str,
    booking: BookingService,
    memory: ConversationMemory,
    db: AsyncSession,
) -> ChatResponse:
    """Process one step of the booking flow and return a ChatResponse."""
    step_hint, actions = await booking.process_step(session_id, message, db)

    # ── Rescheduling policy: answer the question, then offer to resume booking ──
    if step_hint == "rescheduling_policy":
        from app.services.known_topics import _build_topic_data
        policy = _build_topic_data("rescheduling")
        history = await memory.get_history(session_id)
        answer = await llm_service.generate_known_topic_answer(
            message, "rescheduling", policy, history
        )
        answer = llm_service.strip_citations(answer)
        answer += "\n\nBy the way, you still have a booking in progress — just let me know when you'd like to continue!"
        # Offer to resume the in-progress booking
        actions = [
            {"label": "Continue Booking", "value": "continue", "action_type": "booking"},
            {"label": "Cancel Booking", "value": "Cancel", "action_type": "quick_reply"},
        ]
        await memory.add_exchange(session_id, message, answer)
        return ChatResponse(
            answer=answer,
            citations=[],
            session_id=session_id,
            confidence="high",
            max_similarity=None,
            actions=[Action(**a) for a in actions],
        )

    # Get booking data for LLM context
    state_data = await booking._get_state(session_id)
    booking_data = booking.get_booking_summary(state_data)

    # Get conversation history for continuity
    history = await memory.get_history(session_id)

    # Generate natural language for this step
    answer = await llm_service.generate_booking_text(step_hint, booking_data, history)
    answer = llm_service.strip_citations(answer)

    # Mark session so post-booking messages don't push more booking CTAs
    if step_hint == "booked":
        await memory.set_meta(session_id, {"recently_booked": True})

    # Store exchange in memory
    await memory.add_exchange(session_id, message, answer)

    return ChatResponse(
        answer=answer,
        citations=[],
        session_id=session_id,
        confidence="high",
        max_similarity=None,
        actions=[Action(**a) for a in actions],
    )


# ── Known-topic fallback helper ───────────────────────────────────

async def _handle_known_topic(
    question: str,
    session_id: str,
    memory: ConversationMemory,
    booking: BookingService,
    history: List[Dict[str, str]],
    patient_type: Optional[str],
    max_similarity: Optional[float] = None,
    verified_patient: Optional[Dict] = None,
    cache_service=None,
    kb_version: Optional[int] = None,
    recently_booked: bool = False,
) -> Optional[ChatResponse]:
    """
    Try to answer from known clinic topics (services, hours, etc.).
    Returns a ChatResponse if a topic matches, otherwise None.
    """
    result = detect_known_topic(question)
    if not result:
        return None

    topic_name, topic_data = result

    # "booking" topic → redirect to booking flow (only if truly a booking intent)
    if topic_name == "booking":
        if not BookingService.is_booking_intent(question):
            return None  # "book" appeared but user is uncertain/asking — not a real booking intent
        inferred_service = _infer_service_from_history(history)
        inferred_consultation = _infer_consultation_from_history(history)
        step_hint, actions = await booking.start(
            session_id, verified_patient=verified_patient, message=question,
            inferred_service=inferred_service,
            inferred_consultation=inferred_consultation,
        )
        state_data = await booking._get_state(session_id)
        booking_data = booking.get_booking_summary(state_data)
        answer = await llm_service.generate_booking_text(
            step_hint, booking_data, history
        )
        await memory.add_exchange(session_id, question, answer)
        return ChatResponse(
            answer=answer,
            citations=[],
            session_id=session_id,
            confidence="high",
            max_similarity=None,
            actions=[Action(**a) for a in actions],
        )

    # Generate warm answer from config data
    answer = await llm_service.generate_known_topic_answer(
        question, topic_name, topic_data, history
    )
    answer = llm_service.strip_citations(answer)
    actions = _generate_contextual_actions(question, answer, patient_type, recently_booked=recently_booked)
    await memory.add_exchange(session_id, question, answer)

    # Cache the known-topic response so repeats are served from cache
    if cache_service and kb_version is not None:
        await cache_service.set_response(question, kb_version, {
            'answer': answer,
            'citations': [],
            'confidence': 'medium',
            'max_similarity': max_similarity,
        })

    return ChatResponse(
        answer=answer,
        citations=[],
        session_id=session_id,
        confidence="medium",
        max_similarity=max_similarity,
        actions=actions,
    )


# ── Main endpoint ─────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[redis.Redis] = Depends(get_redis),
):
    """
    Chat endpoint with 4-way routing:
    0. Patient type detection → welcome flow
    1. Active booking flow → state machine
    2. Booking intent detected → start booking
    3. General chat → RAG pipeline with known-topic fallback
    """
    t0 = time.monotonic()
    try:
        question = request.message
        session_id = request.session_id or str(uuid.uuid4())
        kb_version = settings.kb_version

        def _ms() -> int:
            return int((time.monotonic() - t0) * 1000)

        # Services
        memory = ConversationMemory(redis_client)
        booking = BookingService(redis_client)
        cache_service = get_cache_service(redis_client)

        # Load session metadata for patient type
        meta = await memory.get_meta(session_id)
        patient_type = meta.get("patient_type")
        recently_booked = meta.get("recently_booked", False)

        # ── Route 0: Verification & patient type detection ─────
        verification_state = meta.get("verification_state")
        msg_lower = question.strip().lower()

        # 0a. Awaiting phone input from returning patient
        if verification_state == "awaiting_phone":
            history = await memory.get_history(session_id)

            # Allow "continue as guest" to exit verification
            if "continue as guest" in msg_lower:
                await memory.set_meta(session_id, {"verification_state": "guest"})
                answer = await llm_service.generate_known_topic_answer(
                    question, "welcome_returning", {}, history
                )
                actions = [
                    Action(label="Book Follow-up", value="I'd like to book an appointment", action_type="booking"),
                    Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
                ]
                await memory.add_exchange(session_id, question, answer)
                asyncio.create_task(_record_analytics(
                    session_id=session_id, question=question, answer=answer,
                    response_source="patient_type", route_taken="verification",
                    confidence="high", patient_type=patient_type, response_time_ms=_ms(),
                ))
                return ChatResponse(
                    answer=answer, citations=[], session_id=session_id,
                    confidence="high", max_similarity=None, actions=actions,
                )

            # Allow "try again" to re-prompt for phone
            _RETRY_DURING_PHONE = ["try again", "try another", "re-enter", "enter again"]
            if any(p in msg_lower for p in _RETRY_DURING_PHONE):
                answer = PHONE_PROMPT_TEXT
                actions = [
                    Action(label="Continue as Guest", value="continue as guest", action_type="quick_reply"),
                ]
                await memory.add_exchange(session_id, question, answer)
                asyncio.create_task(_record_analytics(
                    session_id=session_id, question=question, answer=answer,
                    response_source="patient_type", route_taken="verification",
                    confidence="high", patient_type=patient_type, response_time_ms=_ms(),
                ))
                return ChatResponse(
                    answer=answer, citations=[], session_id=session_id,
                    confidence="high", max_similarity=None, actions=actions,
                )

            if not is_valid_phone_input(question):
                answer = PHONE_INVALID_TEXT
                actions = [
                    Action(label="Try Again", value="try again", action_type="quick_reply"),
                    Action(label="Continue as Guest", value="continue as guest", action_type="quick_reply"),
                ]
                await memory.add_exchange(session_id, question, answer)
                asyncio.create_task(_record_analytics(
                    session_id=session_id, question=question, answer=answer,
                    response_source="patient_type", route_taken="verification",
                    confidence="high", patient_type=patient_type, response_time_ms=_ms(),
                ))
                return ChatResponse(
                    answer=answer, citations=[], session_id=session_id,
                    confidence="high", max_similarity=None, actions=actions,
                )

            patient = lookup_patient_by_phone(question)
            if patient:
                await memory.set_meta(session_id, {
                    "verification_state": "verified",
                    "verified_patient": patient,
                })
                answer = await llm_service.generate_known_topic_answer(
                    question, "welcome_verified", patient, history
                )
                actions = [
                    Action(
                        label="patient_profile",
                        value=json.dumps(patient),
                        action_type="patient_card",
                    ),
                ] + _build_verified_patient_actions(patient)
            else:
                await memory.set_meta(session_id, {"verification_state": "failed"})
                answer = PHONE_NO_MATCH_TEXT
                actions = [
                    Action(label="Try Again", value="try another number", action_type="quick_reply"),
                    Action(label="Continue as Guest", value="continue as guest", action_type="quick_reply"),
                ]

            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="patient_type", route_taken="verification",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer, citations=[], session_id=session_id,
                confidence="high", max_similarity=None, actions=actions,
            )

        # 0b. Failed verification — user wants to try again
        _RETRY_PHRASES = ["try again", "try another", "different number", "try a different", "enter again", "re-enter"]
        if verification_state == "failed" and any(p in msg_lower for p in _RETRY_PHRASES):
            await memory.set_meta(session_id, {"verification_state": "awaiting_phone"})
            answer = PHONE_PROMPT_TEXT
            actions = [
                Action(label="Continue as Guest", value="continue as guest", action_type="quick_reply"),
            ]
            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="patient_type", route_taken="verification",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer, citations=[], session_id=session_id,
                confidence="high", max_similarity=None, actions=actions,
            )

        # 0c. Continue as guest (from verification flow)
        if "continue as guest" in msg_lower and patient_type == "returning":
            await memory.set_meta(session_id, {"verification_state": "guest"})
            history = await memory.get_history(session_id)
            answer = await llm_service.generate_known_topic_answer(
                question, "welcome_returning", {}, history
            )
            actions = [
                Action(label="Book Follow-up", value="I'd like to book an appointment", action_type="booking"),
                Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
            ]
            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="patient_type", route_taken="verification",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer, citations=[], session_id=session_id,
                confidence="high", max_similarity=None, actions=actions,
            )

        # 0d. Patient type detection (only if not already set)
        detected = _detect_patient_type(question) if not patient_type else None
        if detected:
            await memory.set_meta(session_id, {"patient_type": detected})
            patient_type = detected
            history = await memory.get_history(session_id)

            if detected == "new":
                topic_data = {"services": settings.clinic_services}
                answer = await llm_service.generate_known_topic_answer(
                    question, "welcome_new", topic_data, history
                )
                actions = [
                    Action(label="Book Initial Consultation", value="I'd like to book an initial consultation", action_type="booking"),
                    Action(label="Naturopathic Medicine", value="Tell me about Naturopathic Medicine", action_type="quick_reply"),
                    Action(label="Acupuncture", value="Tell me about Acupuncture", action_type="quick_reply"),
                    Action(label="Massage Therapy", value="Tell me about Massage Therapy", action_type="quick_reply"),
                    Action(label="IV Therapy", value="Tell me about IV Nutrient Therapy", action_type="quick_reply"),
                ]
            else:
                # Returning patient → ask for phone number
                await memory.set_meta(session_id, {"verification_state": "awaiting_phone"})
                answer = PHONE_PROMPT_TEXT
                actions = [
                    Action(label="Continue as Guest", value="continue as guest", action_type="quick_reply"),
                ]

            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="patient_type", route_taken="patient_type",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence="high",
                max_similarity=None,
                actions=actions,
            )

        # ── Route 0e: Verified patient asking about upcoming appointment ──
        verified_patient = meta.get("verified_patient")
        if verified_patient and _is_upcoming_appointment_query(question) and verified_patient.get("upcoming_appointment"):
            history = await memory.get_history(session_id)
            answer = await llm_service.generate_known_topic_answer(
                question, "upcoming_appointment",
                {"patient": verified_patient},
                history,
            )
            first_name = verified_patient["name"].split()[0]
            actions = [
                Action(label="Reschedule", value="I'd like to reschedule my upcoming appointment", action_type="quick_reply"),
                Action(label="How to Prepare", value=f"How should I prepare for my {verified_patient['upcoming_appointment'].split(' — ')[-1].lower()} session?", action_type="quick_reply"),
                Action(label="Book Another Visit", value="I'd like to book an appointment", action_type="booking"),
            ]
            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="patient_profile", route_taken="upcoming_appointment",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer, citations=[], session_id=session_id,
                confidence="high", max_similarity=None, actions=actions,
            )

        # ── Route 1: Active booking flow ──────────────────────
        if await booking.is_active(session_id):
            # Don't intercept valid booking step responses as known-topic side questions.
            # E.g. "Meet & Greet" is both a consultation topic AND a booking button click.
            _booking_step_values = {s.lower() for s in settings.clinic_services}
            _booking_step_values.update(opt["label"].lower() for opt in CONSULTATION_OPTIONS)
            _booking_step_values.update({
                "not sure", "no preference", "continue", "cancel",
                "confirm", "yes", "no", "confirm booking",
                "back to services", "back", "show services",
                "in-person", "virtual",
                # No-preference phrases for practitioner step
                "any", "anyone", "either", "whoever", "whichever",
                "doesn't matter", "doesnt matter", "don't mind", "dont mind",
                # Date navigation
                "show more dates", "earlier dates",
            })
            # Also pass through date/time navigation phrases
            _date_nav_phrases = (
                "later", "more dates", "next week", "further", "other dates",
                "anything else", "something else", "different date", "not these",
                "none of these", "earlier dates", "show more",
                "earlier", "sooner",
                # Time preference phrases
                "morning", "afternoon", "evening", "after work", "before lunch",
                "show all times", "all times",
            )
            if any(phrase in msg_lower for phrase in _date_nav_phrases):
                _booking_step_values.add(msg_lower)

            # Pass through natural-language no-preference phrases at practitioner step
            _no_pref_phrases = (
                "any doctor", "any practitioner", "any therapist",
                "any of them", "either one", "whoever is",
                "don't care", "dont care", "you choose", "you pick",
                "no particular", "up to you",
                "anyone is fine", "any is fine", "doctor is fine",
            )
            if any(phrase in msg_lower for phrase in _no_pref_phrases):
                _booking_step_values.add(msg_lower)

            # Pass through consultation/service selection phrases during booking
            # so they reach process_step instead of being intercepted as known topics
            _service_selection_phrases = (
                "meet and greet", "meet & greet", "free meet",
                "initial consultation", "initial naturopathic",
                "initial injection", "initial iv", "iv consultation",
                "naturopathic medicine", "massage therapy", "acupuncture",
                "massage", "osteopath",
            )
            if any(phrase in msg_lower for phrase in _service_selection_phrases):
                _booking_step_values.add(msg_lower)

            # Allow general questions without breaking the booking flow.
            # BUT skip the known-topic intercept if the message expresses booking intent
            # (e.g. "no, I want to book meet and greet") — let process_step handle mid-flow restarts.
            # Exception: rescheduling questions should always be answered even with booking words.
            _has_booking_intent = BookingService.is_booking_intent(question)
            known = None
            if msg_lower not in _booking_step_values:
                known = detect_known_topic(question)
                # If booking intent, only keep rescheduling topics — others (consultations,
                # services) should go to process_step for mid-flow handling
                if known and _has_booking_intent and known[0] != "rescheduling":
                    known = None
            if known and known[0] != "booking":
                topic_name, topic_data = known
                history = await memory.get_history(session_id)
                answer = await llm_service.generate_known_topic_answer(
                    question, topic_name, topic_data, history
                )
                answer += "\n\nBy the way, you still have a booking in progress — just let me know when you'd like to continue!"
                await memory.add_exchange(session_id, question, answer)

                # Get current booking state to re-show the right buttons
                state_data = await booking._get_state(session_id)
                state = state_data.get("state", "idle")
                actions = [
                    Action(label="Continue Booking", value="continue", action_type="booking"),
                    Action(label="Cancel Booking", value="Cancel", action_type="quick_reply"),
                ]

                asyncio.create_task(_record_analytics(
                    session_id=session_id, question=question, answer=answer,
                    response_source="known_topic", route_taken="booking",
                    confidence="medium", patient_type=patient_type, response_time_ms=_ms(),
                ))
                return ChatResponse(
                    answer=answer,
                    citations=[],
                    session_id=session_id,
                    confidence="medium",
                    max_similarity=None,
                    actions=actions,
                )

            # ── Side question via RAG ──────────────────────────
            # Catch questions that don't match known topics and answer via RAG.
            # Prevents "invalid_date"/"invalid_phone" when users ask mid-booking.
            if (msg_lower not in _booking_step_values
                    and not _has_booking_intent
                    and ("?" in question or any(msg_lower.startswith(s) for s in _QUESTION_STARTERS))):
                state_data = await booking._get_state(session_id)
                current_state = state_data.get("state", "idle")
                # Only intercept beyond select_service (which has its own handlers)
                if current_state not in ("idle", "booked", "select_service"):
                    history = await memory.get_history(session_id)
                    try:
                        query_embedding = await embedding_service.embed_text(question)
                        retrieval_result = await cache_service.get_retrieval(
                            query_embedding, kb_version, settings.top_k
                        )
                        if not retrieval_result:
                            retrieval_result = await retrieve_with_confidence(
                                query_embedding, db,
                                top_k=settings.top_k, kb_version=kb_version,
                            )
                            await cache_service.set_retrieval(
                                query_embedding, kb_version, settings.top_k, retrieval_result
                            )
                        chunks = retrieval_result['chunks']
                        is_confident = retrieval_result['is_confident']
                        max_sim = retrieval_result['max_similarity']
                        if chunks:
                            answer = await llm_service.generate_answer(
                                question, chunks, is_confident, history=history
                            )
                            if "KB_INSUFFICIENT_INFO" not in answer:
                                answer = llm_service.strip_citations(answer)
                                answer += "\n\nBy the way, you still have a booking in progress — just let me know when you'd like to continue!"
                                await memory.add_exchange(session_id, question, answer)
                                confidence = "high" if is_confident else "medium"
                                asyncio.create_task(_record_analytics(
                                    session_id=session_id, question=question, answer=answer,
                                    response_source="llm", route_taken="booking_side_question",
                                    confidence=confidence, max_similarity=max_sim,
                                    chunk_count=len(chunks),
                                    patient_type=patient_type, response_time_ms=_ms(),
                                ))
                                return ChatResponse(
                                    answer=answer, citations=[], session_id=session_id,
                                    confidence=confidence, max_similarity=max_sim,
                                    actions=[
                                        Action(label="Continue Booking", value="continue", action_type="booking"),
                                        Action(label="Cancel Booking", value="Cancel", action_type="quick_reply"),
                                    ],
                                )
                    except Exception as e:
                        logger.warning(f"Side question RAG failed during booking: {e}")

            # ── Affirmative after side question → resume or infer selection ──
            _AFFIRM_SET = {
                "sure", "yep", "yeah", "yes", "ok", "okay", "perfect",
                "cool", "alright", "fine", "great", "thanks", "got it",
            }
            _AFFIRM_PHRASES = (
                "sounds good", "let's do it", "lets do it", "go ahead",
                "let's go", "lets go", "i'd like that", "i would like that",
                "that sounds great", "that would be great", "yes please",
                "thats fine", "that's fine", "got it thanks",
            )
            is_affirm_msg = (
                set(msg_lower.split()) & _AFFIRM_SET
                or any(p in msg_lower for p in _AFFIRM_PHRASES)
            )
            if is_affirm_msg and msg_lower not in _booking_step_values:
                history = await memory.get_history(session_id)
                last_bot_msg = ""
                for msg in reversed(history):
                    if msg.get("role") == "assistant":
                        last_bot_msg = msg["content"]
                        break

                if "you still have a booking in progress" in last_bot_msg.lower():
                    # Side question was just answered → resume current step
                    question = "continue"
                    logger.info("Affirmative after side question → resuming booking via 'continue'")
                else:
                    # No side question — try to infer service at select_service step
                    state_data = await booking._get_state(session_id)
                    current_state = state_data.get("state", "idle")
                    if current_state == "select_service":
                        _CONSULT_MAP = {
                            "meet and greet": "Meet & Greet",
                            "meet & greet": "Meet & Greet",
                            "initial naturopathic": "Initial Naturopathic Consultation",
                            "initial injection": "Initial Injection/IV Consultation",
                            "initial iv": "Initial Injection/IV Consultation",
                        }
                        for msg in reversed(history):
                            if msg.get("role") == "assistant":
                                bot_text = msg["content"].lower()
                                for phrase, label in _CONSULT_MAP.items():
                                    if phrase in bot_text:
                                        question = label
                                        logger.info(f"Affirmative after side question → auto-selecting '{label}'")
                                        break
                                else:
                                    # Check for service keywords
                                    for kw, svc in SERVICE_KEYWORDS.items():
                                        if word_match(kw, bot_text):
                                            question = svc
                                            logger.info(f"Affirmative after side question → auto-selecting '{svc}'")
                                            break
                                break

            resp = await _handle_booking_step(
                session_id, question, booking, memory, db
            )
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=resp.answer,
                response_source="booking", route_taken="booking",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return resp

        # ── Route 2: Booking intent ──────────────────────────
        if BookingService.is_booking_intent(question):
            # Clear the post-booking flag — user explicitly wants to book again
            if recently_booked:
                await memory.set_meta(session_id, {"recently_booked": False})
                recently_booked = False
            verified_patient = meta.get("verified_patient")
            history = await memory.get_history(session_id)
            inferred_service = _infer_service_from_history(history)
            inferred_consultation = _infer_consultation_from_history(history)
            step_hint, actions = await booking.start(
                session_id, verified_patient=verified_patient, message=question,
                inferred_service=inferred_service,
                inferred_consultation=inferred_consultation,
            )
            state_data = await booking._get_state(session_id)
            booking_data = booking.get_booking_summary(state_data)
            answer = await llm_service.generate_booking_text(
                step_hint, booking_data, history
            )
            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="booking", route_taken="booking_intent",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence="high",
                max_similarity=None,
                actions=[Action(**a) for a in actions],
            )

        # ── Route 2b: Contextual booking (user affirming a booking offer) ──
        history = await memory.get_history(session_id)
        if _is_contextual_booking_intent(question, history):
            if recently_booked:
                await memory.set_meta(session_id, {"recently_booked": False})
                recently_booked = False
            verified_patient = meta.get("verified_patient")
            inferred_service = _infer_service_from_history(history)
            inferred_consultation = _infer_consultation_from_history(history)
            step_hint, actions = await booking.start(
                session_id, verified_patient=verified_patient, message=question,
                inferred_service=inferred_service,
                inferred_consultation=inferred_consultation,
            )
            state_data = await booking._get_state(session_id)
            booking_data = booking.get_booking_summary(state_data)
            answer = await llm_service.generate_booking_text(
                step_hint, booking_data, history
            )
            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="booking", route_taken="contextual_booking",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence="high",
                max_similarity=None,
                actions=[Action(**a) for a in actions],
            )

        # ── Route 3: General chat (RAG) ──────────────────────

        # Load conversation history
        history = await memory.get_history(session_id)

        # Try known topics first (faster than RAG for common questions)
        known_resp = await _handle_known_topic(
            question, session_id, memory, booking, history,
            patient_type, verified_patient=meta.get("verified_patient"),
            cache_service=cache_service, kb_version=kb_version,
            recently_booked=recently_booked,
        )
        if known_resp:
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=known_resp.answer,
                response_source="known_topic", route_taken="rag",
                confidence=known_resp.confidence,
                patient_type=patient_type, response_time_ms=_ms(),
            ))
            return known_resp

        # ── Unknown practitioner short-circuit ──────────────
        # Detect questions about people not on our team BEFORE the RAG pipeline,
        # because the LLM may hallucinate plausible answers from unrelated chunks.
        _unknown_name = _extract_unknown_practitioner(question)
        if _unknown_name:
            team_names = ", ".join(practitioner_services.keys())
            answer = (
                f"I'm sorry, I don't have {_unknown_name} listed on our team. "
                f"Our current practitioners are: {team_names}. "
                "Would you like to learn more about any of them, or can I help with something else?"
            )
            actions = [
                Action(label="Meet the Team", value="Who are your practitioners?", action_type="quick_reply"),
                _smart_booking_action(patient_type),
            ]
            await memory.add_exchange(session_id, question, answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="unknown_practitioner", route_taken="rag",
                confidence="high", patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer, citations=[], session_id=session_id,
                confidence="high", max_similarity=None, actions=actions,
            )

        # Always check response cache before embedding+retrieval
        cached_response = await cache_service.get_response(question, kb_version)
        if cached_response:
            logger.info("Returning cached response")
            cached_answer = llm_service.strip_citations(cached_response['answer'])
            actions = _generate_contextual_actions(
                question, cached_answer, patient_type,
                recently_booked=recently_booked,
            )
            resp = ChatResponse(
                answer=cached_answer,
                citations=[],
                session_id=session_id,
                confidence=cached_response['confidence'],
                max_similarity=cached_response.get('max_similarity'),
                actions=actions,
            )
            await memory.add_exchange(session_id, question, cached_answer)
            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=cached_answer,
                response_source="cache_hit", route_taken="rag",
                confidence=cached_response['confidence'],
                max_similarity=cached_response.get('max_similarity'),
                patient_type=patient_type, response_time_ms=_ms(),
            ))
            return resp

        # ── Context-aware query augmentation ──────────────
        # Referential questions ("these options", "the difference", "which one")
        # lose context when embedded in isolation. Prepend the topic from the
        # last exchange so the embedding captures the right intent.
        _REFERENTIAL_CUES = (
            "these options", "those options", "the options", "the difference",
            "which one", "which is", "what's the difference", "whats the difference",
            "between them", "between these", "between those",
            "all these", "all those", "any of these", "any of those",
            "the first", "the second", "the third",
            "this one", "that one", "the above",
        )
        embed_query = question
        if any(cue in msg_lower for cue in _REFERENTIAL_CUES) and history:
            # Extract topic from last assistant message
            last_assistant = None
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    last_assistant = msg["content"]
                    break
            if last_assistant:
                # Use first 200 chars of last answer as context hint
                context_hint = last_assistant[:200].replace("\n", " ")
                embed_query = f"{context_hint} — {question}"
                logger.info(f"Augmented referential query with conversation context")

        # Embed query
        logger.info(f"Processing query: {question[:100]}...")
        try:
            query_embedding = await embedding_service.embed_text(embed_query)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            raise HTTPException(status_code=500, detail="Failed to process query")

        # Check retrieval cache
        retrieval_result = await cache_service.get_retrieval(
            query_embedding, kb_version, settings.top_k
        )

        # Vector search if cache miss
        if not retrieval_result:
            logger.info("Retrieval cache miss, performing vector search")
            try:
                retrieval_result = await retrieve_with_confidence(
                    query_embedding, db,
                    top_k=settings.top_k,
                    kb_version=kb_version,
                )
                await cache_service.set_retrieval(
                    query_embedding, kb_version, settings.top_k, retrieval_result
                )
            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
                raise HTTPException(status_code=500, detail="Failed to retrieve information")

        chunks = retrieval_result['chunks']
        is_confident = retrieval_result['is_confident']
        max_similarity = retrieval_result['max_similarity']

        # Handle no chunks at all
        if not chunks:
            logger.warning(f"No chunks retrieved (max_similarity={max_similarity:.3f})")

            # Try known-topic fallback
            known_resp = await _handle_known_topic(
                question, session_id, memory, booking, history,
                patient_type, max_similarity,
                verified_patient=meta.get("verified_patient"),
                cache_service=cache_service, kb_version=kb_version,
                recently_booked=recently_booked,
            )
            if known_resp:
                asyncio.create_task(_record_analytics(
                    session_id=session_id, question=question, answer=known_resp.answer,
                    response_source="known_topic", route_taken="rag",
                    confidence=known_resp.confidence, is_knowledge_gap=True,
                    max_similarity=max_similarity, chunk_count=0,
                    patient_type=patient_type, response_time_ms=_ms(),
                ))
                return known_resp

            # Truly unknown — check if it's about an unknown practitioner
            _unknown_name2 = _extract_unknown_practitioner(question)
            if _unknown_name2:
                team_names = ", ".join(practitioner_services.keys())
                answer = (
                    f"I'm sorry, I don't have {_unknown_name2} listed on our team. "
                    f"Our current practitioners are: {team_names}. "
                    "Would you like to learn more about any of them, or can I help with something else?"
                )
                actions = [
                    Action(label="Meet the Team", value="Who are your practitioners?", action_type="quick_reply"),
                    _smart_booking_action(patient_type),
                ]
            else:
                answer = (
                    "I'm not sure I have enough info to answer that well, "
                    "but feel free to ask me about our services, hours, or anything "
                    "else about Nova Clinic!"
                )
                actions = _generate_contextual_actions(question, answer, patient_type, recently_booked=recently_booked)
            await memory.add_exchange(session_id, question, answer)

            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="fallback", route_taken="rag",
                confidence="low", is_knowledge_gap=True,
                max_similarity=max_similarity, chunk_count=0,
                patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence='low',
                max_similarity=max_similarity,
                actions=actions,
            )

        # For low confidence, try known topics first but still fall through
        # to LLM with available chunks if no known topic matches
        if not is_confident:
            logger.info(f"Low confidence retrieval (max_similarity={max_similarity:.3f}), trying known topics")
            known_resp = await _handle_known_topic(
                question, session_id, memory, booking, history,
                patient_type, max_similarity,
                verified_patient=meta.get("verified_patient"),
                cache_service=cache_service, kb_version=kb_version,
                recently_booked=recently_booked,
            )
            if known_resp:
                asyncio.create_task(_record_analytics(
                    session_id=session_id, question=question, answer=known_resp.answer,
                    response_source="known_topic", route_taken="rag",
                    confidence=known_resp.confidence,
                    max_similarity=max_similarity, chunk_count=len(chunks),
                    patient_type=patient_type, response_time_ms=_ms(),
                ))
                return known_resp
            # No known topic — continue to LLM with whatever chunks we have.
            # The LLM + guidelines will handle it appropriately.
            logger.info("No known topic match, passing low-confidence chunks to LLM")

        # For referential questions, augment the question with what was shown
        llm_question = question
        if any(cue in msg_lower for cue in _REFERENTIAL_CUES) and history:
            for msg in reversed(history):
                if msg.get("role") == "assistant" and "[Options shown:" in msg["content"]:
                    # Extract the options note
                    opt_match = re.search(r'\[Options shown: (.+?)\]', msg["content"])
                    if opt_match:
                        llm_question = (
                            f"The patient was just shown these options: {opt_match.group(1)}. "
                            f"They are now asking: {question}"
                        )
                    break

        # Generate answer with LLM (includes history)
        logger.info(f"Generating answer with {len(chunks)} chunks")
        try:
            answer = await llm_service.generate_answer(
                llm_question, chunks, is_confident, history=history
            )
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate answer")

        # Check if LLM indicated insufficient info — try known topics
        if "KB_INSUFFICIENT_INFO" in answer:
            logger.warning("LLM indicated insufficient knowledge base info")

            known_resp = await _handle_known_topic(
                question, session_id, memory, booking, history,
                patient_type, max_similarity,
                verified_patient=meta.get("verified_patient"),
                cache_service=cache_service, kb_version=kb_version,
                recently_booked=recently_booked,
            )
            if known_resp:
                asyncio.create_task(_record_analytics(
                    session_id=session_id, question=question, answer=known_resp.answer,
                    response_source="known_topic", route_taken="rag",
                    confidence=known_resp.confidence, is_knowledge_gap=True,
                    max_similarity=max_similarity, chunk_count=len(chunks),
                    patient_type=patient_type, response_time_ms=_ms(),
                ))
                return known_resp

            _unknown_name3 = _extract_unknown_practitioner(question)
            if _unknown_name3:
                team_names = ", ".join(practitioner_services.keys())
                answer = (
                    f"I'm sorry, I don't have {_unknown_name3} listed on our team. "
                    f"Our current practitioners are: {team_names}. "
                    "Would you like to learn more about any of them, or can I help with something else?"
                )
                actions = [
                    Action(label="Meet the Team", value="Who are your practitioners?", action_type="quick_reply"),
                    _smart_booking_action(patient_type),
                ]
            else:
                answer = (
                    "I'm not sure I have enough info to answer that well, "
                    "but feel free to ask me about our services, hours, or anything "
                    "else about Nova Clinic!"
                )
                actions = _generate_contextual_actions(question, answer, patient_type, recently_booked=recently_booked)
            await memory.add_exchange(session_id, question, answer)

            response_data = {
                'answer': answer,
                'citations': [],
                'confidence': 'low',
                'max_similarity': max_similarity,
            }
            await cache_service.set_response(question, kb_version, response_data)

            asyncio.create_task(_record_analytics(
                session_id=session_id, question=question, answer=answer,
                response_source="fallback", route_taken="rag",
                confidence="low", is_knowledge_gap=True,
                max_similarity=max_similarity, chunk_count=len(chunks),
                patient_type=patient_type, response_time_ms=_ms(),
            ))
            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence='low',
                max_similarity=max_similarity,
                actions=actions,
            )

        # Strip any residual UUIDs from patient-facing text
        answer = llm_service.strip_citations(answer)

        # Detect soft knowledge gaps — LLM admits it doesn't know but didn't use KB_INSUFFICIENT_INFO.
        # These phrases are specific enough to avoid false positives on normal answers,
        # so we check regardless of retrieval confidence (related chunks can have high
        # similarity but still not contain the actual answer).
        _KNOWLEDGE_GAP_PHRASES = [
            "i'm not able to confirm", "i am not able to confirm",
            "i can't confirm", "i cannot confirm",
            "i can't guarantee", "i cannot guarantee",
            "i'm unable to", "i am unable to",
            "i don't have specific information", "i don't have information",
            "i don't have details", "i don't have enough information",
            "i'm not sure i have enough", "i am not sure i have enough",
            "not available in our records", "not in our knowledge",
            "i recommend contacting the clinic directly",
            "contacting the clinic directly",
            "contact the clinic directly",
            "contact us directly",
            "reach out to the clinic directly",
            "reach out directly",
            "call the clinic directly",
        ]
        _is_gap = any(
            phrase in answer.lower() for phrase in _KNOWLEDGE_GAP_PHRASES
        )

        # Contextual actions
        actions = _generate_contextual_actions(question, answer, patient_type, recently_booked=recently_booked)
        confidence = 'high' if is_confident else 'medium'

        # Cache full response for future identical questions
        response_data = {
            'answer': answer,
            'citations': [],
            'confidence': confidence,
            'max_similarity': max_similarity,
        }
        await cache_service.set_response(question, kb_version, response_data)

        # Store exchange in memory (include action labels for referential context)
        stored_answer = answer
        action_labels = [a.label for a in actions if a.label not in ("← Back", "Our Services")]
        if action_labels:
            stored_answer += "\n\n[Options shown: " + " | ".join(action_labels) + "]"
        await memory.add_exchange(session_id, question, stored_answer)

        logger.info("Successfully generated answer")

        asyncio.create_task(_record_analytics(
            session_id=session_id, question=question, answer=answer,
            response_source="llm", route_taken="rag",
            confidence=confidence, max_similarity=max_similarity,
            chunk_count=len(chunks), patient_type=patient_type,
            response_time_ms=_ms(), is_knowledge_gap=_is_gap,
        ))
        return ChatResponse(
            answer=answer,
            citations=[],
            session_id=session_id,
            confidence=confidence,
            max_similarity=max_similarity,
            actions=actions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
