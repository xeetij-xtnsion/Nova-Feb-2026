from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from typing import List, Dict, Optional
from datetime import datetime
import re
import logging
from app.config import settings
from app.services.guidelines import get_guidelines

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are Nova, a warm and friendly virtual assistant for Nova Clinic. You remember what patients have said earlier in the conversation and build on it naturally.

PERSONALITY:
- Speak like a caring receptionist who genuinely wants to help
- Use "we" and "our" when referring to the clinic
- Be warm and encouraging — patients may be nervous!
- You have a gentle sense of humor when appropriate

RESPONSE GUIDELINES:
- Keep answers concise (2-4 sentences) unless the patient asks for detail
- Reference earlier parts of the conversation when relevant ("As I mentioned...", "Since you were asking about...")
- End with a natural follow-up question or offer, not a generic one
- If conversation history is provided, DO NOT repeat information you've already shared

HANDLING SHORT OR AMBIGUOUS MESSAGES:
- If the patient sends a very short or vague message like "no", "ok", "sure", "thanks", "hmm", or similar that does NOT contain a clear question or request, do NOT assume they want information or pretend to know their intent
- Instead, respond naturally and briefly. For example: "No worries! What can I help you with?" or "Of course! Is there anything else you'd like to know?"
- Match the tone of their message — a "no" should get a brief, respectful acknowledgment, not an enthusiastic information dump
- NEVER say things like "I'm glad you're looking for more information" unless they actually asked for information

RULES:
- Answer using ONLY the provided knowledge base context
- If context is insufficient AND the patient's message is a clear question, respond: "KB_INSUFFICIENT_INFO"
- If the patient's message is not a clear question (e.g. "no", "ok", "yeah"), respond conversationally without using KB_INSUFFICIENT_INFO
- Never fabricate information
"""

BOOKING_SYSTEM_PROMPT = """You are Nova, a warm and friendly assistant helping a patient book an appointment at Nova Clinic. Generate ONLY the conversational text for the current booking step. Be brief and encouraging.

Do NOT include any buttons, options lists, or action items — the system handles those automatically. Just write the natural language message (1-2 sentences max)."""

KNOWN_TOPIC_SYSTEM_PROMPT = """You are Nova, a warm and friendly virtual assistant for Nova Clinic. Answer the patient's question using ONLY the clinic information provided below. Keep your response concise (2-3 sentences), warm, and helpful. Do NOT cite sources or use [chunk_id] format — this is known clinic information, not knowledge-base data. End with a brief, natural follow-up offer."""

SENTIMENT_SYSTEM_PROMPT = """Classify the sentiment of the following user message as exactly one word: positive, neutral, or negative. Respond with ONLY that single word."""

WELCOME_TEMPLATES = {
    "welcome_new": (
        "Great, welcome aboard! We offer a range of services including "
        "{services}. "
        "Would you like to book your first visit, or can I tell you more about any of these?"
    ),
    "welcome_returning": (
        "Welcome back! Great to see you again. "
        "How can I help you today — would you like to book a follow-up or do you have any questions?"
    ),
}

PHONE_PROMPT_TEXT = (
    "Welcome back! To pull up your account and personalize your experience, "
    "could you please share the phone number we have on file for you?"
)

PHONE_NO_MATCH_TEXT = (
    "Hmm, I wasn't able to find an account with that number. "
    "Would you like to try a different number, or continue as a guest?"
)

PHONE_INVALID_TEXT = (
    "That doesn't look like a complete phone number — could you double-check "
    "and enter the 10-digit number we have on file?"
)


class LLMService:
    """Service for generating answers using Claude or OpenAI."""

    def __init__(self):
        self.provider = settings.llm_provider
        self.max_tokens = settings.max_tokens

        if self.provider == "anthropic":
            self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            self.model = settings.claude_model
            logger.info(f"LLM provider: Anthropic ({self.model})")
        else:
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.model = settings.openai_llm_model
            logger.info(f"LLM provider: OpenAI ({self.model})")

    async def _call_llm(
        self,
        system: str,
        messages: List[Dict[str, str]],
        max_tokens: int = None,
    ) -> str:
        """Unified LLM call that works with both Anthropic and OpenAI."""
        if max_tokens is None:
            max_tokens = self.max_tokens

        if self.provider == "anthropic":
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text
        else:
            # OpenAI: system prompt goes as first message
            oai_messages = [{"role": "system", "content": system}]
            oai_messages.extend(messages)
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=oai_messages,
            )
            return response.choices[0].message.content

    def _format_context(self, chunks: List[Dict]) -> str:
        """Format retrieved chunks into context for the LLM."""
        context_parts = []
        for chunk in chunks:
            chunk_id = chunk['chunk_id']
            source = chunk.get('source_file', 'Unknown')
            heading = chunk.get('section_heading', 'N/A')
            content = chunk['content']
            context_parts.append(
                f"[{chunk_id}]\n"
                f"Source: {source}\n"
                f"Section: {heading}\n"
                f"Content: {content}\n"
            )
        return "\n---\n".join(context_parts)

    async def generate_answer(
        self,
        question: str,
        chunks: List[Dict],
        is_confident: bool = True,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate an answer with optional conversation history."""
        context = self._format_context(chunks)

        user_prompt = f"""Context from knowledge base:

{context}

---

Question: {question}

Please answer the question based on the context above."""

        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        try:
            system = SYSTEM_PROMPT + get_guidelines()
            answer = await self._call_llm(system, messages)
            answer = self.strip_markdown(answer)
            logger.info(f"Generated answer (length: {len(answer)} chars)")
            return answer
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            raise

    async def generate_booking_text(
        self,
        step_hint: str,
        booking_data: Dict,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate natural language text for a booking step."""
        prompt = self._booking_prompt(step_hint, booking_data)
        messages = []
        if history:
            messages.extend(history[-4:])
        messages.append({"role": "user", "content": prompt})

        try:
            system = BOOKING_SYSTEM_PROMPT + get_guidelines()
            answer = await self._call_llm(system, messages, max_tokens=256)
            return self.strip_markdown(answer)
        except Exception as e:
            logger.warning(f"Booking LLM failed, using fallback: {e}")
            return self._fallback_booking_text(step_hint, booking_data)

    @staticmethod
    def _friendly_date(iso: str) -> str:
        """Convert '2026-02-16' to '16th Feb, 2026'."""
        if not iso:
            return ""
        try:
            d = datetime.strptime(iso, "%Y-%m-%d").date()
            n = d.day
            suffix = "th" if 11 <= n <= 13 else ["th","st","nd","rd","th","th","th","th","th","th"][n % 10]
            return f"{n}{suffix} {d.strftime('%b')}, {d.year}"
        except ValueError:
            return iso

    @staticmethod
    def _booking_prompt(step_hint: str, data: Dict) -> str:
        """Build a short prompt telling the LLM what step we're on."""
        pract = data.get('practitioner')
        pract_note = f" with {pract}" if pract else ""
        fdate = LLMService._friendly_date(data.get('date', ''))
        mode = data.get('delivery_mode', '')
        mode_note = f" ({mode})" if mode else ""
        mode_mention = f" Mention that this will be a {mode} appointment." if mode else ""
        prompts = {
            "select_service": "The patient wants to book an appointment. Ask them which service they'd like. Available services will be shown as buttons.",
            "select_consultation_type": "The patient wants to book a consultation. Ask them which type of consultation they'd prefer — the options (Initial Naturopathic Consultation, Initial Injection/IV Consultation, or a free Meet & Greet) will appear as buttons. Keep it brief and warm.",
            "recommend_consult": "The patient isn't sure which service to pick. First, genuinely reassure them — say something like 'That's totally fine!' or 'No worries at all!'. Then briefly explain that we offer a few consultation options to help them figure out the best path, including a free 15-minute Meet & Greet with no commitment. Do NOT list the options — buttons will appear automatically. Keep it warm, short, and low-pressure.",
            "select_delivery_mode": f"The patient chose '{data.get('service_display') or data.get('service', '')}'. Ask how they'd like to attend — the delivery mode options (e.g. In-person, Phone, Virtual) will appear as buttons.",
            "select_practitioner": f"The patient chose '{data.get('service', '')}'{mode_note}.{mode_mention} Ask if they have a preferred practitioner. Practitioner buttons will appear automatically along with a 'No preference' option.",
            "select_date": f"The patient chose '{data.get('service', '')}'{mode_note}{pract_note}. Now ask them to pick a date. Date buttons will appear automatically.",
            "select_time": f"The patient chose {fdate} for {data.get('service', '')}{mode_note}{pract_note}. Ask them to pick a time slot.",
            "suggest_time": f"The patient asked about time preferences for their {data.get('service', '')} on {fdate}{pract_note}. Based on what they said, here are the best matching time slots — the buttons will show automatically. Briefly acknowledge their preference and ask them to pick from these options.",
            "collect_name": f"The patient selected {data.get('time', '')} on {fdate} for {data.get('service', '')}{mode_note}{pract_note}. Ask for their full name.",
            "collect_phone": f"The patient's name is {data.get('name', '')}. Now ask for their phone number.",
            "confirm": f"Summarize the booking and ask the patient to confirm: {data.get('service', '')}{mode_note}{pract_note} on {fdate} at {data.get('time', '')} for {data.get('name', '')}.",
            "booked": f"The appointment is confirmed! {data.get('service', '')}{mode_note}{pract_note} on {fdate} at {data.get('time', '')} for {data.get('name', '')}. Warmly confirm, say we look forward to seeing them, and let them know they can reach out if they have any questions or need to make changes before their visit.",
            "cancelled": "The patient cancelled the booking. Acknowledge kindly and let them know they can book anytime.",
            "invalid_service": "The patient picked an invalid service. Gently ask them to select from the buttons below.",
            "invalid_delivery_mode": "The patient picked an invalid delivery mode. Gently ask them to select from the buttons below.",
            "invalid_practitioner": "The patient picked an invalid practitioner. Gently ask them to select from the buttons below or choose 'No preference'.",
            "invalid_date": "The patient entered an invalid date. Kindly ask them to pick from the available dates shown.",
            "invalid_time": "The patient entered an invalid time. Ask them to select one of the available time slots.",
            "invalid_name": "The name was too short. Ask the patient to enter their full name.",
            "invalid_phone": "The phone number doesn't look right. Ask them to re-enter a valid phone number.",
            "booking_error": "Something went wrong saving the appointment. Apologize and ask them to try again.",
            "select_practitioner_with_preferred": f"The patient chose '{data.get('service', '')}'{mode_note}.{mode_mention} They usually see {data.get('preferred_practitioner', 'their preferred practitioner')} — mention that they're listed first. Ask if they'd like to continue with them or choose someone else. Practitioner buttons will appear automatically.",
            "confirm_prefilled": f"Summarize the booking and ask the patient to confirm: {data.get('service', '')}{mode_note}{pract_note} on {fdate} at {data.get('time', '')} for {data.get('name', '')}. Their name and phone are already on file so you don't need to re-confirm those details.",
            "booking_confused": "The patient seems unsure or is reconsidering during the booking. Warmly acknowledge that it's totally okay to take a step back. Let them know they can continue where they left off, explore our services, or cancel — no pressure at all.",
            "practitioner_confused": f"The patient isn't sure which practitioner to choose for {data.get('service', '')}. Briefly reassure them — they can pick 'No preference' and we'll match them with someone great, or they can choose from the list. Keep it warm and low-pressure.",
            "ambiguous_practitioner": "The patient typed a practitioner name that matches more than one person. Let them know we found a few matches and ask them to pick the right one from the buttons below.",
        }
        return prompts.get(step_hint, "Continue the booking conversation naturally.")

    @staticmethod
    def _fallback_booking_text(step_hint: str, data: Dict) -> str:
        """Static fallback text when LLM is unavailable."""
        pract = data.get('practitioner')
        pract_note = f" with {pract}" if pract else ""
        pract_line = f"  Practitioner: {pract}\n" if pract else ""
        mode = data.get('delivery_mode', '')
        mode_line = f"  Delivery Mode: {mode}\n" if mode else ""
        mode_note = f" ({mode})" if mode else ""
        fdate = LLMService._friendly_date(data.get('date', ''))
        fallbacks = {
            "select_service": "Great, let's get you booked! Which service would you like?",
            "select_consultation_type": "Let's get you booked for a consultation! Which type would you prefer?",
            "recommend_consult": "That's totally fine — no worries at all! We have a few consultation options to help you figure out the best path, including a free 15-minute Meet & Greet with no commitment. Take a look and see what feels right!",
            "select_delivery_mode": f"How would you like to attend your {data.get('service_display') or data.get('service', '')} appointment?",
            "select_practitioner": f"Wonderful choice — {data.get('service', '')}! This will be a {mode} appointment. Do you have a preferred practitioner?" if mode else f"Wonderful choice — {data.get('service', '')}! Do you have a preferred practitioner?",
            "select_date": f"Perfect! Which date works best for you?",
            "select_time": f"Got it, {fdate}. What time would you prefer?",
            "suggest_time": f"Sure! Here are the later time slots we have available on {fdate}. Which one works best for you?",
            "collect_name": "Almost there! Could I get your full name, please?",
            "collect_phone": f"Thanks, {data.get('name', '')}! And what's the best phone number to reach you?",
            "confirm": (
                f"Here's your booking summary:\n"
                f"  Service: {data.get('service', '')}\n"
                f"{mode_line}"
                f"{pract_line}"
                f"  Date: {fdate}\n"
                f"  Time: {data.get('time', '')}\n"
                f"  Name: {data.get('name', '')}\n"
                f"  Phone: {data.get('phone', '')}\n\n"
                f"Shall I confirm this appointment?"
            ),
            "booked": f"You're all set! Your {data.get('service', '')}{mode_note} appointment{pract_note} is booked for {fdate} at {data.get('time', '')}. We look forward to seeing you! If you have any questions or need to make changes before your visit, don't hesitate to reach out.",
            "cancelled": "No worries at all! Feel free to book whenever you're ready.",
            "invalid_service": "Hmm, I didn't catch that. Could you pick one of the services below?",
            "invalid_delivery_mode": "I didn't catch that. Could you pick one of the delivery options below?",
            "invalid_practitioner": "I didn't catch that. Could you pick one of the practitioners below, or choose 'No preference'?",
            "invalid_date": "That date doesn't seem right. Could you pick one of the dates below?",
            "invalid_time": "I didn't recognize that time slot. Please choose from the options below.",
            "invalid_name": "Could you enter your full name? It should be at least 2 characters.",
            "invalid_phone": "That phone number doesn't look quite right. Please enter a valid number with at least 7 digits.",
            "booking_error": "I'm sorry, something went wrong saving your appointment. Please try again!",
            "select_practitioner_with_preferred": f"Great choice — {data.get('service', '')}! This will be a {mode} appointment. I see you usually see {data.get('preferred_practitioner', 'your preferred practitioner')} — they're listed first below. Would you like to continue with them, or choose someone else?" if mode else f"Great choice — {data.get('service', '')}! I see you usually see {data.get('preferred_practitioner', 'your preferred practitioner')} — they're listed first below. Would you like to continue with them, or choose someone else?",
            "confirm_prefilled": (
                f"Here's your booking summary:\n"
                f"  Service: {data.get('service', '')}\n"
                f"{mode_line}"
                f"{pract_line}"
                f"  Date: {fdate}\n"
                f"  Time: {data.get('time', '')}\n"
                f"  Name: {data.get('name', '')} (on file)\n"
                f"  Phone: {data.get('phone', '')} (on file)\n\n"
                f"Shall I confirm this appointment?"
            ),
            "booking_confused": "No worries at all! There's no rush. You can continue where you left off, explore our services to learn more, or cancel — whatever feels right for you.",
            "practitioner_confused": f"No problem! If you're not sure, you can choose 'No preference' and we'll match you with a great practitioner for your {data.get('service', '')} appointment. Or feel free to pick from the list below!",
            "ambiguous_practitioner": "I found a few practitioners matching that name. Could you pick the right one from the options below?",
        }
        return fallbacks.get(step_hint, "How can I help you with your booking?")

    @staticmethod
    def _build_verified_welcome(patient: Dict) -> str:
        """Build a personalized greeting for a verified returning patient.

        The detailed profile data is rendered as a card by the frontend
        via the patient_card action — this just returns the greeting text.
        """
        first_name = patient["name"].split()[0]
        return (
            f"Welcome back, {first_name}! Great to see you again. "
            "Here's your account summary — how can I help you today?"
        )

    @staticmethod
    def _build_upcoming_appointment_answer(patient: Dict) -> str:
        """Build a confident answer about the patient's upcoming appointment."""
        first_name = patient["name"].split()[0]
        upcoming = patient.get("upcoming_appointment", "")
        practitioner = patient.get("preferred_practitioner", "")

        # Parse "Feb 24 — Acupuncture" format
        parts = upcoming.split(" — ", 1) if " — " in upcoming else [upcoming, ""]
        date_part = parts[0].strip()
        service_part = parts[1].strip() if len(parts) > 1 else ""

        answer = f"Your upcoming appointment is on {date_part} for {service_part}."
        if practitioner:
            answer += f" You'll be seeing {practitioner}."
        answer += " If you'd like to reschedule or have any questions about preparing for your visit, just let me know!"
        return answer

    async def generate_known_topic_answer(
        self,
        question: str,
        topic: str,
        topic_data: Dict,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate an answer for a known topic using clinic config data."""
        # Handle verified patient welcome (deterministic, no LLM call)
        if topic == "welcome_verified":
            return self._build_verified_welcome(topic_data)

        # Handle upcoming appointment query for verified patients
        if topic == "upcoming_appointment":
            patient = topic_data.get("patient", {})
            return self._build_upcoming_appointment_answer(patient)

        # Handle welcome templates directly (no LLM call needed)
        if topic.startswith("welcome_"):
            template = WELCOME_TEMPLATES.get(topic, "")
            if template and "services" in topic_data:
                return template.format(
                    services=", ".join(topic_data["services"])
                )
            return template

        detail = topic_data.get("detail", "")
        prompt = (
            f"Clinic information:\n{detail}\n\n"
            f"Patient question: {question}\n\n"
            f"Answer warmly using the clinic information above."
        )

        messages = []
        if history:
            messages.extend(history[-4:])
        messages.append({"role": "user", "content": prompt})

        try:
            system = KNOWN_TOPIC_SYSTEM_PROMPT + get_guidelines()
            result = await self._call_llm(system, messages, max_tokens=256)
            return self.strip_markdown(result)
        except Exception as e:
            logger.warning(f"Known-topic LLM failed, using fallback: {e}")
            return detail or "I can help you with that — please ask me about our services, hours, or booking!"

    async def analyze_sentiment(self, question: str) -> Optional[str]:
        """Classify a user message as positive, neutral, or negative."""
        try:
            truncated = question[:500]
            response = await self._call_llm(
                SENTIMENT_SYSTEM_PROMPT,
                [{"role": "user", "content": truncated}],
                max_tokens=4,
            )
            label = response.strip().lower()
            if label in {"positive", "neutral", "negative"}:
                return label
            return "neutral"
        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return None

    def extract_citations(self, answer: str, chunks: List[Dict]) -> List[Dict]:
        """Extract citation references from the answer and map to source metadata."""
        citation_pattern = r'\[([a-f0-9\-]{36})\]'
        cited_ids = re.findall(citation_pattern, answer)

        if not cited_ids:
            return []

        chunk_map = {chunk['chunk_id']: chunk for chunk in chunks}

        citations = []
        seen_ids = set()
        for chunk_id in cited_ids:
            if chunk_id in seen_ids:
                continue
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                citations.append({
                    'chunk_id': chunk_id,
                    'source_file': chunk.get('source_file', 'Unknown'),
                    'section_heading': chunk.get('section_heading', 'N/A'),
                    'chunk_index': chunk.get('chunk_index', 0),
                })
                seen_ids.add(chunk_id)

        logger.info(f"Extracted {len(citations)} unique citations from answer")
        return citations

    @staticmethod
    def strip_markdown(text: str) -> str:
        """Remove markdown formatting (bold, italic, headers) from text."""
        # Remove bold/italic markers
        text = text.replace("**", "")
        text = text.replace("*", "")
        # Remove markdown headers (##, ###)
        text = re.sub(r'^#{1,4}\s+', '', text, flags=re.MULTILINE)
        return text

    @staticmethod
    def strip_citations(answer: str) -> str:
        """Remove [chunk_id] UUID references from the answer text."""
        # Remove UUIDs and any trailing comma/space combos left behind
        cleaned = re.sub(r'\s*\[([a-f0-9\-]{36})\]\s*,?\s*', ' ', answer)
        # Clean up double spaces and trailing whitespace
        cleaned = re.sub(r'  +', ' ', cleaned).strip()
        return cleaned


# Global instance
llm_service = LLMService()
