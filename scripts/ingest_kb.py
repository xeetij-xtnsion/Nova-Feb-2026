#!/usr/bin/env python3
"""
Knowledge base ingestion script.

Ingests .docx files from kb/sources/ directory, chunks them,
creates embeddings, and stores in the database.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.models.database import KBChunk
from app.utils.docx_parser import parse_docx
from app.services.chunking import create_chunks_from_sections
from app.services.embedding import embedding_service
from sqlalchemy import select, delete
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def ingest_document(file_path: str, kb_version: int = None) -> int:
    """
    Ingest a single .docx document.

    Args:
        file_path: Path to the .docx file
        kb_version: Knowledge base version (defaults to settings.kb_version)

    Returns:
        Number of chunks created
    """
    if kb_version is None:
        kb_version = settings.kb_version

    source_file = os.path.basename(file_path)
    logger.info(f"Processing {source_file}...")

    # Parse document
    try:
        sections = parse_docx(file_path)
    except Exception as e:
        logger.error(f"Failed to parse {source_file}: {e}")
        return 0

    if not sections:
        logger.warning(f"No sections found in {source_file}")
        return 0

    # Create chunks
    chunks = create_chunks_from_sections(sections, source_file, kb_version)

    if not chunks:
        logger.warning(f"No chunks created from {source_file}")
        return 0

    logger.info(f"Created {len(chunks)} chunks, generating embeddings...")

    # Generate embeddings
    texts = [chunk['content'] for chunk in chunks]
    try:
        embeddings = await embedding_service.embed_batch(texts)
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        return 0

    # Add embeddings to chunks
    for chunk, embedding in zip(chunks, embeddings):
        chunk['embedding'] = embedding

    # Store in database
    async with AsyncSessionLocal() as session:
        try:
            # Delete existing chunks for this file and version
            await session.execute(
                delete(KBChunk).where(
                    KBChunk.source_file == source_file,
                    KBChunk.kb_version == kb_version
                )
            )

            # Insert new chunks
            for chunk in chunks:
                db_chunk = KBChunk(**chunk)
                session.add(db_chunk)

            await session.commit()
            logger.info(f"✓ Ingested {len(chunks)} chunks from {source_file}")
            return len(chunks)

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to store chunks in database: {e}")
            return 0


async def ingest_all(sources_dir: str = "kb/sources", kb_version: int = None):
    """
    Ingest all .docx files from the sources directory.

    Args:
        sources_dir: Directory containing .docx files
        kb_version: Knowledge base version (defaults to settings.kb_version)
    """
    if kb_version is None:
        kb_version = settings.kb_version

    logger.info("Initializing database...")
    await init_db()

    sources_path = Path(sources_dir)
    if not sources_path.exists():
        logger.error(f"Sources directory not found: {sources_dir}")
        return

    # Find all .docx files
    docx_files = list(sources_path.glob("*.docx"))
    if not docx_files:
        logger.warning(f"No .docx files found in {sources_dir}")
        return

    logger.info(f"Found {len(docx_files)} .docx file(s)")

    total_chunks = 0
    for file_path in docx_files:
        chunks = await ingest_document(str(file_path), kb_version)
        total_chunks += chunks

    logger.info(f"\n✓ Ingestion complete! Total chunks: {total_chunks}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest knowledge base documents")
    parser.add_argument(
        "--sources",
        default="kb/sources",
        help="Directory containing .docx files (default: kb/sources)"
    )
    parser.add_argument(
        "--version",
        type=int,
        default=None,
        help="KB version number (default: from config)"
    )

    args = parser.parse_args()

    asyncio.run(ingest_all(args.sources, args.version))


if __name__ == "__main__":
    main()
