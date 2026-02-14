import uuid
from typing import List, Dict
import re
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Heading patterns that indicate AI guidelines/instructions (not patient-facing content)
_GUIDELINE_PATTERNS = [
    r'\bai\s+rule\b',
    r'\bai\s+action\b',
    r'\bai\s+guidance\b',
    r'\bai\s+safety\b',
    r'\bai\s+clarification\b',
    r'\bai\s+escalation\b',
    r'\bimportant\s+ai\b',
    r'\brequired\s+ai\b',
    r'\bai\s+guardrail',
    r'\bsafety\s*&\s*scope\s+boundaries\b',
    r'\bescalation\s+trigger',
    r'\bbooking\s+mistakes.*guardrail',
    r'\bcommon\s+booking\s+mistakes\b',
    r'\bhow\s+the\s+ai\b',
    r'\binternal\s+safety\b',
    r'\binternal\s+compliance\b',
    r'\binternal\s+guidance\b',
    r'\brequired.*response\s+pattern\b',
    r'\bdo\s+not\s+expose\b',
    r'\bbooking\s+rules?\b',
    r'\bbooking\s+guidance\b',
]


def is_guideline_heading(heading: str) -> bool:
    """Check if a section heading indicates AI guideline content."""
    heading_lower = heading.lower()
    return any(re.search(p, heading_lower) for p in _GUIDELINE_PATTERNS)


def chunk_section(
    section_heading: str,
    section_text: str,
    chunk_size: int = None,
    chunk_overlap: int = None
) -> List[Dict]:
    """
    Split a section into chunks with overlap, preserving sentence boundaries.

    Args:
        section_heading: The heading for this section
        section_text: The text content of the section
        chunk_size: Maximum chunk size (defaults to settings.chunk_size)
        chunk_overlap: Overlap between chunks (defaults to settings.chunk_overlap)

    Returns:
        List of chunk dictionaries with heading, text, and metadata
    """
    if chunk_size is None:
        chunk_size = settings.chunk_size
    if chunk_overlap is None:
        chunk_overlap = settings.chunk_overlap

    # If text is shorter than chunk size, return as single chunk
    if len(section_text) <= chunk_size:
        return [{
            'section_heading': section_heading,
            'content': section_text,
        }]

    # Split into sentences (look for . ! ? followed by space or end of string)
    sentences = re.split(r'(?<=[.!?])\s+', section_text)

    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence_length = len(sentence)

        # If adding this sentence would exceed chunk_size
        if current_length + sentence_length > chunk_size and current_chunk:
            # Save current chunk
            chunks.append(' '.join(current_chunk))

            # Start new chunk with overlap
            # Keep sentences from end of previous chunk that fit in overlap
            overlap_chunk = []
            overlap_length = 0
            for s in reversed(current_chunk):
                if overlap_length + len(s) <= chunk_overlap:
                    overlap_chunk.insert(0, s)
                    overlap_length += len(s) + 1  # +1 for space
                else:
                    break

            current_chunk = overlap_chunk
            current_length = overlap_length

        # Add sentence to current chunk
        current_chunk.append(sentence)
        current_length += sentence_length + 1  # +1 for space

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))

    # Convert to chunk dictionaries
    result = []
    for chunk_text in chunks:
        result.append({
            'section_heading': section_heading,
            'content': chunk_text.strip(),
        })

    logger.debug(f"Split section '{section_heading}' into {len(result)} chunks")
    return result


def create_chunks_from_sections(
    sections: List[Dict[str, str]],
    source_file: str,
    kb_version: int = None
) -> List[Dict]:
    """
    Create chunks from document sections with metadata.

    Args:
        sections: List of {heading, text} dictionaries
        source_file: Name of source file
        kb_version: Knowledge base version (defaults to settings.kb_version)

    Returns:
        List of chunk dictionaries ready for storage
    """
    if kb_version is None:
        kb_version = settings.kb_version

    all_chunks = []
    chunk_index = 0

    for section in sections:
        section_chunks = chunk_section(
            section['heading'],
            section['text']
        )

        guideline = is_guideline_heading(section['heading'])
        for chunk in section_chunks:
            all_chunks.append({
                'chunk_id': str(uuid.uuid4()),
                'source_file': source_file,
                'section_heading': chunk['section_heading'],
                'chunk_index': chunk_index,
                'content': chunk['content'],
                'kb_version': kb_version,
                'is_guideline': guideline,
            })
            chunk_index += 1

    guideline_count = sum(1 for c in all_chunks if c['is_guideline'])
    logger.info(
        f"Created {len(all_chunks)} chunks from {source_file} "
        f"({guideline_count} guideline chunks)"
    )
    return all_chunks
