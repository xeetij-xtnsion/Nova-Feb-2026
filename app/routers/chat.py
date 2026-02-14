from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from typing import Optional, List, Dict
import uuid
import logging

from app.schemas.chat import ChatRequest, ChatResponse, Citation, Action
from app.database import get_db
from app.redis_client import get_redis
from app.services.embedding import embedding_service
from app.services.retrieval import retrieve_with_confidence
from app.services.llm import llm_service
from app.services.cache import get_cache_service
from app.services.memory import ConversationMemory
from app.services.booking import BookingService
from app.services.known_topics import detect_known_topic
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Patient type detection ────────────────────────────────────────

NEW_PATIENT_KEYWORDS = ["new patient", "first time", "first visit", "never been", "i'm new"]
RETURNING_PATIENT_KEYWORDS = ["returning", "been here before", "came before", "follow-up", "follow up", "been before", "visited before", "i'm returning"]


def _detect_patient_type(message: str) -> Optional[str]:
    """Return 'new' or 'returning' if the message indicates patient type."""
    msg = message.lower()
    if any(kw in msg for kw in NEW_PATIENT_KEYWORDS):
        return "new"
    if any(kw in msg for kw in RETURNING_PATIENT_KEYWORDS):
        return "returning"
    return None


# ── Contextual action helpers ─────────────────────────────────────

EMERGENCY_KEYWORDS = [
    "emergency", "heart attack", "call 911", "call 9-1-1",
    "seek immediate", "immediate medical", "paralyz", "paralys",
    "stroke", "chest pain", "can't breathe", "cannot breathe",
    "severe bleeding", "unconscious", "suicide", "overdose",
]

# ── Broad topic actions (matched on QUESTION only) ────────────────

_BROAD_TOPIC_ACTIONS: List[tuple] = [
    # (keywords_to_match, actions)
    (["service", "offer", "treatment", "provide", "what do you do"], [
        Action(label="Naturopathic Medicine", value="Tell me about Naturopathic Medicine", action_type="quick_reply"),
        Action(label="Acupuncture", value="Tell me about Acupuncture", action_type="quick_reply"),
        Action(label="Massage Therapy", value="Tell me about Massage Therapy", action_type="quick_reply"),
        Action(label="IV Therapy", value="Tell me about IV Nutrient Therapy", action_type="quick_reply"),
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
    ]),
    (["hour", "open", "close", "when are you"], [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
        Action(label="Where are you?", value="Where is the clinic located?", action_type="quick_reply"),
    ]),
    (["cost", "price", "fee", "how much", "pricing", "afford", "insurance"], [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
    ]),
    (["location", "address", "where", "direction", "parking", "find you"], [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Hours", value="What are your hours of operation?", action_type="quick_reply"),
    ]),
    (["doctor", "practitioner", "staff", "team", "therapist", "who works"], [
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
    ]),
]

# ── Service-specific sub-actions (matched on question + answer) ───

_BACK_BTN = Action(label="\u2190 Back", value="What services do you offer?", action_type="back")

_SERVICE_ACTIONS: List[tuple] = [
    # Massage Therapy — show duration options
    (["massage"], [
        Action(label="30 min — $75", value="Tell me about a 30-minute massage", action_type="quick_reply"),
        Action(label="60 min — $120", value="Tell me about a 60-minute massage", action_type="quick_reply"),
        Action(label="90 min — $160", value="Tell me about a 90-minute massage", action_type="quick_reply"),
        Action(label="Book Massage", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Acupuncture — show types
    (["acupuncture", "acupunctur"], [
        Action(label="Classic Acupuncture", value="Tell me about classic acupuncture sessions", action_type="quick_reply"),
        Action(label="Body Cupping — $70", value="Tell me about body cupping therapy", action_type="quick_reply"),
        Action(label="Facial Rejuvenation", value="Tell me about facial rejuvenation acupuncture", action_type="quick_reply"),
        Action(label="Book Acupuncture", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Cupping
    (["cupping"], [
        Action(label="Body Cupping — $70", value="What does body cupping involve and how much does it cost?", action_type="quick_reply"),
        Action(label="Acupuncture + Cupping", value="Can I combine acupuncture with cupping?", action_type="quick_reply"),
        Action(label="Book Cupping", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Facial Rejuvenation
    (["facial rejuvenation", "facial acupuncture"], [
        Action(label="Rejuvenating Facial", value="Tell me about rejuvenating facial acupuncture and pricing", action_type="quick_reply"),
        Action(label="Non-Needle Facial — $80", value="Tell me about the non-needle facial acupuncture option", action_type="quick_reply"),
        Action(label="Book Facial", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Naturopathic Medicine
    (["naturopath"], [
        Action(label="Initial Visit — $295", value="What happens at an initial naturopathic consultation?", action_type="quick_reply"),
        Action(label="Follow-Up Options", value="What are the follow-up appointment options and pricing for naturopathic visits?", action_type="quick_reply"),
        Action(label="Free Meet & Greet", value="Do you offer a free meet and greet with a naturopathic doctor?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # IV Therapy
    (["iv therapy", "iv nutrient", "iv drip", "iv treatment", "intravenous"], [
        Action(label="IV Drip Options", value="What IV drip options do you offer and what are the prices?", action_type="quick_reply"),
        Action(label="IV Push Options", value="Tell me about IV push treatments", action_type="quick_reply"),
        Action(label="Initial IV Consult", value="What's involved in the initial IV therapy consultation?", action_type="quick_reply"),
        Action(label="Book IV Consult", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Injections
    (["injection"], [
        Action(label="Vitamin IM Shot", value="Tell me about vitamin intramuscular injections and pricing", action_type="quick_reply"),
        Action(label="Trigger Point — $150+", value="Tell me about trigger point injection therapy", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Prolotherapy
    (["prolotherap"], [
        Action(label="How it works", value="How does prolotherapy work and what conditions does it treat?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Functional Testing
    (["functional test", "lab test", "hormone test", "food sensitiv", "testing"], [
        Action(label="Types of Tests", value="What types of functional tests do you offer?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    # Pediatric
    (["pediatric", "child", "children", "kid", "infant", "baby", "toddler"], [
        Action(label="Pediatric Naturopathic", value="Tell me about pediatric naturopathic medicine", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
]

# ── Symptom/condition → service suggestions ───────────────────────

_SYMPTOM_ACTIONS: List[tuple] = [
    (["pain", "sore", "muscle", "tension", "back pain", "neck pain", "headache", "migraine", "stiff"], [
        Action(label="Acupuncture", value="Can acupuncture help with pain relief?", action_type="quick_reply"),
        Action(label="Massage Therapy", value="Tell me about massage therapy for pain", action_type="quick_reply"),
        Action(label="Trigger Point Injection", value="Tell me about trigger point injection therapy", action_type="quick_reply"),
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    (["stress", "anxiety", "relax", "sleep", "insomnia", "mental health", "burnout"], [
        Action(label="Acupuncture", value="Can acupuncture help with stress and anxiety?", action_type="quick_reply"),
        Action(label="Massage Therapy", value="Tell me about massage for relaxation", action_type="quick_reply"),
        Action(label="Naturopathic Medicine", value="How can naturopathic medicine help with stress?", action_type="quick_reply"),
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    (["digest", "gut", "bloat", "ibs", "stomach", "nausea", "constipat", "diarr"], [
        Action(label="Naturopathic Medicine", value="How can naturopathic medicine help with digestive issues?", action_type="quick_reply"),
        Action(label="Functional Testing", value="Do you offer digestive or stool analysis tests?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    (["hormone", "thyroid", "fatigue", "energy", "tired", "menopaus", "period", "pcos", "fertil"], [
        Action(label="Naturopathic Medicine", value="How can naturopathic medicine help with hormonal issues?", action_type="quick_reply"),
        Action(label="Hormone Testing", value="Do you offer hormone testing?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    (["skin", "acne", "eczema", "psoriasis", "rash", "wrinkle", "aging", "anti-aging"], [
        Action(label="Facial Rejuvenation", value="Tell me about facial rejuvenation acupuncture", action_type="quick_reply"),
        Action(label="Naturopathic Medicine", value="How can naturopathic medicine help with skin conditions?", action_type="quick_reply"),
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    (["immune", "cold", "flu", "vitamin", "boost", "wellness", "prevent", "detox"], [
        Action(label="IV Therapy", value="Tell me about IV nutrient therapy for immune support", action_type="quick_reply"),
        Action(label="Vitamin Injections", value="Tell me about vitamin intramuscular injections", action_type="quick_reply"),
        Action(label="Naturopathic Medicine", value="How can naturopathic medicine support immunity?", action_type="quick_reply"),
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    (["joint", "ligament", "tendon", "sport", "knee", "shoulder", "elbow", "ankle", "sprain"], [
        Action(label="Prolotherapy", value="How does prolotherapy work for joint issues?", action_type="quick_reply"),
        Action(label="Acupuncture", value="Can acupuncture help with joint pain?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
    (["weight", "diet", "nutrition", "food", "allerg"], [
        Action(label="Naturopathic Medicine", value="How can naturopathic medicine help with weight and nutrition?", action_type="quick_reply"),
        Action(label="Food Sensitivity Testing", value="Do you offer food sensitivity testing?", action_type="quick_reply"),
        Action(label="Book Consultation", value="I'd like to book an appointment", action_type="booking"),
        _BACK_BTN,
    ]),
]

# ── Practitioner names for detection ──────────────────────────────

_PRACTITIONER_KEYWORDS = {
    "ali": "Dr. Ali Nurani",
    "nurani": "Dr. Ali Nurani",
    "marisa": "Dr. Marisa Hucal",
    "hucal": "Dr. Marisa Hucal",
    "chad": "Dr. Chad Patterson",
    "patterson": "Dr. Chad Patterson",
    "alexa": "Dr. Alexa Torontow",
    "torontow": "Dr. Alexa Torontow",
    "lorena": "Lorena Bulcao",
    "bulcao": "Lorena Bulcao",
}


def _generate_contextual_actions(
    question: str, answer: str, patient_type: Optional[str] = None
) -> List[Action]:
    """Return relevant action buttons based on context."""
    q_lower = question.lower()
    combined = (question + " " + answer).lower()

    # 0. Suppress actions for emergency responses
    if any(kw in combined for kw in EMERGENCY_KEYWORDS):
        return []

    # 1. Broad topics — match on QUESTION only to avoid false positives
    for keywords, actions in _BROAD_TOPIC_ACTIONS:
        if any(kw in q_lower for kw in keywords):
            return actions

    # 2. Service-specific sub-actions — match on question + answer
    for keywords, actions in _SERVICE_ACTIONS:
        if any(kw in combined for kw in keywords):
            return actions

    # 3. Symptom/condition detection — match on question + answer
    for keywords, actions in _SYMPTOM_ACTIONS:
        if any(kw in combined for kw in keywords):
            return actions

    # 4. Practitioner mention → offer to book with them
    for keyword, name in _PRACTITIONER_KEYWORDS.items():
        if keyword in combined:
            return [
                Action(label=f"Book with {name.split()[0]} {name.split()[-1]}", value="I'd like to book an appointment", action_type="booking"),
                Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
            ]

    # 5. Patient-type-aware fallback
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

    # 6. Generic fallback
    return [
        Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
        Action(label="Book Appointment", value="I'd like to book an appointment", action_type="booking"),
    ]


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

    # Get booking data for LLM context
    state_data = await booking._get_state(session_id)
    booking_data = booking.get_booking_summary(state_data)

    # Get conversation history for continuity
    history = await memory.get_history(session_id)

    # Generate natural language for this step
    answer = await llm_service.generate_booking_text(step_hint, booking_data, history)

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
) -> Optional[ChatResponse]:
    """
    Try to answer from known clinic topics (services, hours, etc.).
    Returns a ChatResponse if a topic matches, otherwise None.
    """
    result = detect_known_topic(question)
    if not result:
        return None

    topic_name, topic_data = result

    # "booking" topic → redirect to booking flow
    if topic_name == "booking":
        step_hint, actions = await booking.start(session_id)
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
    actions = _generate_contextual_actions(question, answer, patient_type)
    await memory.add_exchange(session_id, question, answer)

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
    try:
        question = request.message
        session_id = request.session_id or str(uuid.uuid4())
        kb_version = settings.kb_version

        # Services
        memory = ConversationMemory(redis_client)
        booking = BookingService(redis_client)
        cache_service = get_cache_service(redis_client)

        # Load session metadata for patient type
        meta = await memory.get_meta(session_id)
        patient_type = meta.get("patient_type")

        # ── Route 0: Patient type detection ───────────────────
        detected = _detect_patient_type(question)
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
                    Action(label="Book Initial Consultation", value="I'd like to book an appointment", action_type="booking"),
                    Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
                ]
            else:
                answer = await llm_service.generate_known_topic_answer(
                    question, "welcome_returning", {}, history
                )
                actions = [
                    Action(label="Book Follow-up", value="I'd like to book an appointment", action_type="booking"),
                    Action(label="Our Services", value="What services do you offer?", action_type="quick_reply"),
                ]

            await memory.add_exchange(session_id, question, answer)
            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence="high",
                max_similarity=None,
                actions=actions,
            )

        # ── Route 1: Active booking flow ──────────────────────
        if await booking.is_active(session_id):
            # Allow general questions without breaking the booking flow
            known = detect_known_topic(question)
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
                    Action(label="Cancel Booking", value="__cancel__", action_type="quick_reply"),
                ]

                return ChatResponse(
                    answer=answer,
                    citations=[],
                    session_id=session_id,
                    confidence="medium",
                    max_similarity=None,
                    actions=actions,
                )

            return await _handle_booking_step(
                session_id, question, booking, memory, db
            )

        # ── Route 2: Booking intent ──────────────────────────
        if BookingService.is_booking_intent(question):
            step_hint, actions = await booking.start(session_id)
            state_data = await booking._get_state(session_id)
            booking_data = booking.get_booking_summary(state_data)
            history = await memory.get_history(session_id)
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

        # ── Route 3: General chat (RAG) ──────────────────────

        # Load conversation history
        history = await memory.get_history(session_id)

        # Skip response cache if there's conversation context
        if not history:
            cached_response = await cache_service.get_response(question, kb_version)
            if cached_response:
                logger.info("Returning cached response")
                actions = _generate_contextual_actions(
                    question, cached_response['answer'], patient_type
                )
                resp = ChatResponse(
                    answer=cached_response['answer'],
                    citations=[Citation(**c) for c in cached_response['citations']],
                    session_id=session_id,
                    confidence=cached_response['confidence'],
                    max_similarity=cached_response.get('max_similarity'),
                    actions=actions,
                )
                await memory.add_exchange(session_id, question, cached_response['answer'])
                return resp

        # Embed query
        logger.info(f"Processing query: {question[:100]}...")
        try:
            query_embedding = await embedding_service.embed_text(question)
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
            )
            if known_resp:
                return known_resp

            # Truly unknown — generic fallback
            answer = (
                "I'm not sure I have enough info to answer that well, "
                "but feel free to ask me about our services, hours, or anything "
                "else about Nova Clinic!"
            )
            actions = _generate_contextual_actions(question, answer, patient_type)
            await memory.add_exchange(session_id, question, answer)

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
            )
            if known_resp:
                return known_resp
            # No known topic — continue to LLM with whatever chunks we have.
            # The LLM + guidelines will handle it appropriately.
            logger.info("No known topic match, passing low-confidence chunks to LLM")

        # Generate answer with LLM (includes history)
        logger.info(f"Generating answer with {len(chunks)} chunks")
        try:
            answer = await llm_service.generate_answer(
                question, chunks, is_confident, history=history
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
            )
            if known_resp:
                return known_resp

            answer = (
                "I'm not sure I have enough info to answer that well, "
                "but feel free to ask me about our services, hours, or anything "
                "else about Nova Clinic!"
            )
            actions = _generate_contextual_actions(question, answer, patient_type)
            await memory.add_exchange(session_id, question, answer)

            response_data = {
                'answer': answer,
                'citations': [],
                'confidence': 'low',
                'max_similarity': max_similarity,
            }
            if not history:
                await cache_service.set_response(question, kb_version, response_data)

            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence='low',
                max_similarity=max_similarity,
                actions=actions,
            )

        # Extract citations then strip UUIDs from patient-facing text
        citations_data = llm_service.extract_citations(answer, chunks)
        citations = [Citation(**c) for c in citations_data]
        answer = llm_service.strip_citations(answer)

        # Contextual actions
        actions = _generate_contextual_actions(question, answer, patient_type)
        confidence = 'high' if is_confident else 'medium'

        # Cache full response (only when no history, so it's context-free)
        if not history:
            response_data = {
                'answer': answer,
                'citations': citations_data,
                'confidence': confidence,
                'max_similarity': max_similarity,
            }
            await cache_service.set_response(question, kb_version, response_data)

        # Store exchange in memory
        await memory.add_exchange(session_id, question, answer)

        logger.info(f"Successfully generated answer with {len(citations)} citations")

        return ChatResponse(
            answer=answer,
            citations=citations,
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
