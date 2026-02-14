"""
Guidelines service: loads AI guideline chunks from the KB and provides
a consolidated prompt block that gets injected into every LLM call.

Guidelines are loaded once at startup and cached in memory.
Call `await load_guidelines()` during app startup to populate.
"""

import re
import logging
from typing import Optional
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.database import KBChunk
from app.config import settings

logger = logging.getLogger(__name__)

# In-memory cache of the consolidated guidelines prompt
_guidelines_prompt: Optional[str] = None


# Categories for organizing guidelines in the prompt
_CATEGORY_MAP = {
    "safety": [
        "safety & scope boundaries",
        "safety & scope boundary",
        "internal safety",
        "do not expose",
        "internal compliance",
    ],
    "escalation": [
        "escalation trigger",
        "escalation rule",
    ],
    "booking_guardrails": [
        "booking mistakes",
        "guardrail",
        "booking rules",
        "booking guidance",
    ],
    "ai_behaviour": [
        "ai rule",
        "ai action",
        "ai guidance",
        "ai safety",
        "ai clarification",
        "important ai",
        "required.*response pattern",
        "how the ai",
    ],
}


def _categorize(heading: str) -> str:
    """Assign a guideline chunk to a category based on its heading."""
    h = heading.lower()
    for category, patterns in _CATEGORY_MAP.items():
        for pattern in patterns:
            if pattern in h:
                return category
    return "ai_behaviour"  # default


def _normalize(text: str) -> str:
    """Normalize text for deduplication: lowercase, strip whitespace/punctuation."""
    text = text.lower().strip()
    text = re.sub(r'[❌✅📘•\-–—]+', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def _extract_rules(content: str) -> list[str]:
    """Extract individual rule lines from a chunk's content."""
    lines = content.strip().split('\n')
    rules = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip pure headers within content
        if line.endswith(':') and len(line) < 80:
            continue
        rules.append(line)
    return rules


def _is_duplicate(normalized: str, seen_normalized: set[str]) -> bool:
    """Check if content is duplicate or substantially contained in existing."""
    if normalized in seen_normalized:
        return True
    # Check if this is a substring of something already seen (or vice versa)
    for existing in seen_normalized:
        # If >80% of the shorter string is in the longer one, skip
        shorter, longer = sorted([normalized, existing], key=len)
        if len(shorter) > 20 and shorter in longer:
            return True
    return False


def _build_prompt(chunks: list[dict]) -> str:
    """
    Build a consolidated, deduplicated guidelines prompt.

    Extracts individual rules from chunks, deduplicates across services,
    and organizes into clean categories.
    """
    # Collect unique rules per category
    category_rules: dict[str, list[str]] = {
        "safety": [],
        "escalation": [],
        "booking_guardrails": [],
        "ai_behaviour": [],
    }
    seen_normalized: dict[str, set[str]] = {
        k: set() for k in category_rules
    }

    for chunk in chunks:
        content = chunk["content"].strip()
        category = _categorize(chunk["section_heading"] or "")

        rules = _extract_rules(content)
        for rule in rules:
            norm = _normalize(rule)
            if len(norm) < 5:
                continue
            if _is_duplicate(norm, seen_normalized[category]):
                continue
            seen_normalized[category].add(norm)
            category_rules[category].append(rule)

    sections = []

    if category_rules["safety"]:
        sections.append(
            "## SAFETY & SCOPE BOUNDARIES\n"
            + "\n".join(f"- {r}" for r in category_rules["safety"])
        )

    if category_rules["escalation"]:
        sections.append(
            "## ESCALATION RULES\n"
            + "\n".join(f"- {r}" for r in category_rules["escalation"])
        )

    if category_rules["booking_guardrails"]:
        sections.append(
            "## BOOKING GUARDRAILS\n"
            + "\n".join(f"- {r}" for r in category_rules["booking_guardrails"])
        )

    if category_rules["ai_behaviour"]:
        sections.append(
            "## AI BEHAVIOUR RULES\n"
            + "\n".join(f"- {r}" for r in category_rules["ai_behaviour"])
        )

    if not sections:
        return ""

    return (
        "\n\n--- CLINIC KNOWLEDGE BASE GUIDELINES (ALWAYS FOLLOW) ---\n\n"
        + "\n\n".join(sections)
        + "\n\n--- END GUIDELINES ---"
    )


async def load_guidelines(kb_version: int = None) -> str:
    """
    Load all guideline chunks from the database and build the prompt.

    Call this during app startup after the DB is initialized.
    Returns the consolidated guidelines text.
    """
    global _guidelines_prompt

    if kb_version is None:
        kb_version = settings.kb_version

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                KBChunk.section_heading,
                KBChunk.content,
                KBChunk.chunk_index,
            )
            .where(KBChunk.kb_version == kb_version, KBChunk.is_guideline.is_(True))
            .order_by(KBChunk.chunk_index)
        )
        rows = result.all()

    if not rows:
        logger.warning("No guideline chunks found in KB — system prompt will not include KB guidelines")
        _guidelines_prompt = ""
        return ""

    chunks = [
        {"section_heading": r.section_heading, "content": r.content}
        for r in rows
    ]

    _guidelines_prompt = _build_prompt(chunks)
    logger.info(
        f"Loaded {len(rows)} guideline chunks → consolidated to "
        f"{len(_guidelines_prompt)} chars (~{len(_guidelines_prompt) // 4} tokens)"
    )
    return _guidelines_prompt


def get_guidelines() -> str:
    """Return the cached guidelines prompt. Empty string if not loaded yet."""
    return _guidelines_prompt or ""
