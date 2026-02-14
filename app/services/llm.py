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

CITATIONS:
- Cite sources using [chunk_id] format at the end of sentences
- Only cite when answering from knowledge base context

RULES:
- Answer using ONLY the provided knowledge base context
- If context is insufficient, respond: "KB_INSUFFICIENT_INFO"
- Never fabricate information
"""

BOOKING_SYSTEM_PROMPT = """You are Nova, a warm and friendly assistant helping a patient book an appointment at Nova Clinic. Generate ONLY the conversational text for the current booking step. Be brief and encouraging.

Do NOT include any buttons, options lists, or action items — the system handles those automatically. Just write the natural language message (1-2 sentences max)."""

KNOWN_TOPIC_SYSTEM_PROMPT = """You are Nova, a warm and friendly virtual assistant for Nova Clinic. Answer the patient's question using ONLY the clinic information provided below. Keep your response concise (2-3 sentences), warm, and helpful. Do NOT cite sources or use [chunk_id] format — this is known clinic information, not knowledge-base data. End with a brief, natural follow-up offer."""

WELCOME_TEMPLATES = {
    "welcome_new": (
        "Welcome to Nova Clinic! We're so glad you're here. "
        "We offer {services}. "
        "I'd love to help you learn more about any of these or get you booked for your first visit!"
    ),
    "welcome_returning": (
        "Welcome back to Nova Clinic! It's great to see you again. "
        "How can I help you today — would you like to book a follow-up or do you have any questions?"
    ),
}


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

Please answer the question based on the context above. Remember to cite sources using [chunk_id] format."""

        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        try:
            system = SYSTEM_PROMPT + get_guidelines()
            answer = await self._call_llm(system, messages)
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
            return await self._call_llm(system, messages, max_tokens=256)
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
        prompts = {
            "select_service": "The patient wants to book an appointment. Ask them which service they'd like. Available services will be shown as buttons.",
            "recommend_consult": "The patient isn't sure which service to pick. Warmly reassure them — that's completely okay! Recommend starting with an Initial Consultation where our naturopathic doctor will assess their needs and guide them to the right treatment. The button will appear automatically.",
            "select_practitioner": f"The patient chose '{data.get('service', '')}'. Ask if they have a preferred practitioner. Practitioner buttons will appear automatically along with a 'No preference' option.",
            "select_date": f"The patient chose '{data.get('service', '')}'{pract_note}. Now ask them to pick a date. Date buttons will appear automatically.",
            "select_time": f"The patient chose {fdate} for {data.get('service', '')}{pract_note}. Ask them to pick a time slot.",
            "collect_name": f"The patient selected {data.get('time', '')} on {fdate} for {data.get('service', '')}{pract_note}. Ask for their full name.",
            "collect_phone": f"The patient's name is {data.get('name', '')}. Now ask for their phone number.",
            "confirm": f"Summarize the booking and ask the patient to confirm: {data.get('service', '')}{pract_note} on {fdate} at {data.get('time', '')} for {data.get('name', '')}.",
            "booked": f"The appointment is confirmed! {data.get('service', '')}{pract_note} on {fdate} at {data.get('time', '')} for {data.get('name', '')}. Warmly confirm and say we look forward to seeing them.",
            "cancelled": "The patient cancelled the booking. Acknowledge kindly and let them know they can book anytime.",
            "invalid_service": "The patient picked an invalid service. Gently ask them to select from the buttons below.",
            "invalid_practitioner": "The patient picked an invalid practitioner. Gently ask them to select from the buttons below or choose 'No preference'.",
            "invalid_date": "The patient entered an invalid date. Kindly ask them to pick from the available dates shown.",
            "invalid_time": "The patient entered an invalid time. Ask them to select one of the available time slots.",
            "invalid_name": "The name was too short. Ask the patient to enter their full name.",
            "invalid_phone": "The phone number doesn't look right. Ask them to re-enter a valid phone number.",
            "booking_error": "Something went wrong saving the appointment. Apologize and ask them to try again.",
        }
        return prompts.get(step_hint, "Continue the booking conversation naturally.")

    @staticmethod
    def _fallback_booking_text(step_hint: str, data: Dict) -> str:
        """Static fallback text when LLM is unavailable."""
        pract = data.get('practitioner')
        pract_note = f" with {pract}" if pract else ""
        pract_line = f"  Practitioner: {pract}\n" if pract else ""
        fdate = LLMService._friendly_date(data.get('date', ''))
        fallbacks = {
            "select_service": "Great, let's get you booked! Which service would you like?",
            "recommend_consult": "No worries at all! I'd recommend starting with an Initial Consultation — our naturopathic doctor will assess your needs and recommend the best path forward for you.",
            "select_practitioner": f"Wonderful choice — {data.get('service', '')}! Do you have a preferred practitioner?",
            "select_date": f"Perfect! Which date works best for you?",
            "select_time": f"Got it, {fdate}. What time would you prefer?",
            "collect_name": "Almost there! Could I get your full name, please?",
            "collect_phone": f"Thanks, {data.get('name', '')}! And what's the best phone number to reach you?",
            "confirm": (
                f"Here's your booking summary:\n"
                f"  Service: {data.get('service', '')}\n"
                f"{pract_line}"
                f"  Date: {fdate}\n"
                f"  Time: {data.get('time', '')}\n"
                f"  Name: {data.get('name', '')}\n"
                f"  Phone: {data.get('phone', '')}\n\n"
                f"Shall I confirm this appointment?"
            ),
            "booked": f"You're all set! Your {data.get('service', '')} appointment{pract_note} is booked for {fdate} at {data.get('time', '')}. We look forward to seeing you!",
            "cancelled": "No worries at all! Feel free to book whenever you're ready.",
            "invalid_service": "Hmm, I didn't catch that. Could you pick one of the services below?",
            "invalid_practitioner": "I didn't catch that. Could you pick one of the practitioners below, or choose 'No preference'?",
            "invalid_date": "That date doesn't seem right. Could you pick one of the dates below?",
            "invalid_time": "I didn't recognize that time slot. Please choose from the options below.",
            "invalid_name": "Could you enter your full name? It should be at least 2 characters.",
            "invalid_phone": "That phone number doesn't look quite right. Please enter a valid number with at least 7 digits.",
            "booking_error": "I'm sorry, something went wrong saving your appointment. Please try again!",
        }
        return fallbacks.get(step_hint, "How can I help you with your booking?")

    async def generate_known_topic_answer(
        self,
        question: str,
        topic: str,
        topic_data: Dict,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate an answer for a known topic using clinic config data."""
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
            return await self._call_llm(system, messages, max_tokens=256)
        except Exception as e:
            logger.warning(f"Known-topic LLM failed, using fallback: {e}")
            return detail or "I can help you with that — please ask me about our services, hours, or booking!"

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
    def strip_citations(answer: str) -> str:
        """Remove [chunk_id] UUID references from the answer text."""
        # Remove UUIDs and any trailing comma/space combos left behind
        cleaned = re.sub(r'\s*\[([a-f0-9\-]{36})\]\s*,?\s*', ' ', answer)
        # Clean up double spaces and trailing whitespace
        cleaned = re.sub(r'  +', ' ', cleaned).strip()
        return cleaned


# Global instance
llm_service = LLMService()
