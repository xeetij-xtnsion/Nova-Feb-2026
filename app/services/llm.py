from anthropic import AsyncAnthropic
from typing import List, Dict, Optional
import re
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Service for generating answers using Claude."""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.max_tokens = settings.max_tokens

    def _format_context(self, chunks: List[Dict]) -> str:
        """
        Format retrieved chunks into context for Claude.

        Args:
            chunks: List of chunk dictionaries with content and metadata

        Returns:
            Formatted context string
        """
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
        is_confident: bool = True
    ) -> str:
        """
        Generate an answer using Claude based on retrieved context.

        Args:
            question: User's question
            chunks: Retrieved chunks with content and metadata
            is_confident: Whether retrieval was confident

        Returns:
            Generated answer text
        """
        # Format context
        context = self._format_context(chunks)

        # System prompt emphasizes using only KB content and citing sources
        system_prompt = """You are Nova, a friendly and helpful virtual assistant for Nova Clinic. You're here to help patients learn about our services in a warm, conversational way.

TONE & STYLE:
- Write like you're chatting with a friend - warm, approachable, encouraging
- Use "we" and "our" when talking about the clinic
- Keep responses SHORT (2-3 sentences max for initial answers)
- Use simple, everyday language - avoid medical jargon unless necessary
- Be enthusiastic about helping!

ANSWER STRUCTURE:
1. Start with a brief, direct answer to their question (1-2 sentences)
2. Add ONE key detail if helpful
3. End with a friendly offer: "Would you like to know more about [specific topic]?" or "I can also tell you about [related topic]!"

CITATIONS:
- Always cite sources using [chunk_id] format, but do it naturally
- Place citations at the end of sentences, not mid-sentence

IMPORTANT RULES:
- Answer using ONLY the provided knowledge base context
- If context is insufficient, respond: "KB_INSUFFICIENT_INFO"
- Never make up information or use outside knowledge

Example style:
"We offer acupuncture treatments that can help with pain relief and stress management! [chunk_id] Our licensed practitioners use traditional Chinese medicine techniques. Would you like to know about booking an appointment?"
"""

        # User prompt with context and question
        user_prompt = f"""Context from knowledge base:

{context}

---

Question: {question}

Please answer the question based on the context above. Remember to cite sources using [chunk_id] format."""

        try:
            # Call Claude API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract text from response
            answer = response.content[0].text

            logger.info(f"Generated answer (length: {len(answer)} chars)")
            return answer

        except Exception as e:
            logger.error(f"Error generating answer with Claude: {e}")
            raise

    def extract_citations(self, answer: str, chunks: List[Dict]) -> List[Dict]:
        """
        Extract citation references from the answer and map to source metadata.

        Args:
            answer: Generated answer text with [chunk_id] citations
            chunks: List of chunk dictionaries with metadata

        Returns:
            List of unique citation dictionaries with source metadata
        """
        # Find all [chunk_id] patterns in the answer
        citation_pattern = r'\[([a-f0-9\-]{36})\]'  # UUID pattern
        cited_ids = re.findall(citation_pattern, answer)

        if not cited_ids:
            return []

        # Create a map of chunk_id to metadata
        chunk_map = {
            chunk['chunk_id']: chunk
            for chunk in chunks
        }

        # Build unique citations list
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
                    'chunk_index': chunk.get('chunk_index', 0)
                })
                seen_ids.add(chunk_id)

        logger.info(f"Extracted {len(citations)} unique citations from answer")
        return citations


# Global instance
llm_service = LLMService()
