from docx import Document
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


def parse_docx(file_path: str) -> List[Dict[str, str]]:
    """
    Parse a .docx file and extract sections with headings.

    Args:
        file_path: Path to the .docx file

    Returns:
        List of dictionaries with 'heading' and 'text' keys
        If no headings found, returns single section with heading='Document'
    """
    try:
        doc = Document(file_path)
    except Exception as e:
        logger.error(f"Failed to open document {file_path}: {e}")
        raise

    sections = []
    current_heading = "Document"  # Default heading for text before first heading
    current_text = []

    for paragraph in doc.paragraphs:
        # Check if this is a heading paragraph
        if paragraph.style.name.startswith('Heading'):
            # Save previous section if it has text
            if current_text:
                sections.append({
                    'heading': current_heading,
                    'text': '\n'.join(current_text).strip()
                })
                current_text = []

            # Start new section with this heading
            current_heading = paragraph.text.strip()
        else:
            # Regular paragraph - add to current section
            text = paragraph.text.strip()
            if text:  # Only add non-empty paragraphs
                current_text.append(text)

    # Don't forget the last section
    if current_text:
        sections.append({
            'heading': current_heading,
            'text': '\n'.join(current_text).strip()
        })

    # If no sections found, return empty list
    if not sections:
        logger.warning(f"No content found in document {file_path}")
        return []

    logger.info(f"Parsed {len(sections)} sections from {file_path}")
    return sections
