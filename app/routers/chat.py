from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from typing import Optional
import logging

from app.schemas.chat import ChatRequest, ChatResponse, Citation
from app.database import get_db
from app.redis_client import get_redis
from app.services.embedding import embedding_service
from app.services.retrieval import retrieve_with_confidence
from app.services.llm import llm_service
from app.services.cache import get_cache_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[redis.Redis] = Depends(get_redis)
):
    """
    Chat endpoint - main RAG pipeline.

    Pipeline:
    1. Check response cache
    2. If miss: embed query
    3. Check retrieval cache
    4. If miss: vector search
    5. Assess confidence
    6. Generate answer with Claude
    7. Extract citations
    8. Cache results
    """
    try:
        question = request.message
        session_id = request.session_id
        kb_version = settings.kb_version

        # Initialize cache service
        cache_service = get_cache_service(redis_client)

        # Step 1: Check response cache
        cached_response = await cache_service.get_response(question, kb_version)
        if cached_response:
            logger.info("Returning cached response")
            return ChatResponse(
                answer=cached_response['answer'],
                citations=[Citation(**c) for c in cached_response['citations']],
                session_id=session_id,
                confidence=cached_response['confidence'],
                max_similarity=cached_response.get('max_similarity')
            )

        # Step 2: Embed query
        logger.info(f"Processing query: {question[:100]}...")
        try:
            query_embedding = await embedding_service.embed_text(question)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            raise HTTPException(status_code=500, detail="Failed to process query")

        # Step 3: Check retrieval cache
        retrieval_result = await cache_service.get_retrieval(
            query_embedding,
            kb_version,
            settings.top_k
        )

        # Step 4: Vector search if cache miss
        if not retrieval_result:
            logger.info("Retrieval cache miss, performing vector search")
            try:
                retrieval_result = await retrieve_with_confidence(
                    query_embedding,
                    db,
                    top_k=settings.top_k,
                    kb_version=kb_version
                )
                # Cache retrieval results
                await cache_service.set_retrieval(
                    query_embedding,
                    kb_version,
                    settings.top_k,
                    retrieval_result
                )
            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
                raise HTTPException(status_code=500, detail="Failed to retrieve information")

        chunks = retrieval_result['chunks']
        is_confident = retrieval_result['is_confident']
        max_similarity = retrieval_result['max_similarity']

        # Step 5: Handle low confidence
        if not is_confident or not chunks:
            logger.warning(f"Low confidence retrieval (max_similarity={max_similarity:.3f})")
            answer = (
                "I apologize, but I don't have sufficient information in my knowledge base "
                "to answer your question accurately. Could you please rephrase your question "
                "or ask something else about Nova Clinic's services, hours, or policies?"
            )

            response_data = {
                'answer': answer,
                'citations': [],
                'confidence': 'low',
                'max_similarity': max_similarity
            }

            # Cache the low-confidence response
            await cache_service.set_response(question, kb_version, response_data)

            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence='low',
                max_similarity=max_similarity
            )

        # Step 6: Generate answer with Claude
        logger.info(f"Generating answer with {len(chunks)} chunks")
        try:
            answer = await llm_service.generate_answer(question, chunks, is_confident)
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate answer")

        # Check if LLM indicated insufficient info
        if "KB_INSUFFICIENT_INFO" in answer:
            logger.warning("LLM indicated insufficient knowledge base info")
            answer = (
                "I apologize, but I don't have sufficient information in my knowledge base "
                "to answer your question accurately. Could you please rephrase your question "
                "or ask something else about Nova Clinic's services, hours, or policies?"
            )

            response_data = {
                'answer': answer,
                'citations': [],
                'confidence': 'low',
                'max_similarity': max_similarity
            }

            # Cache the low-confidence response
            await cache_service.set_response(question, kb_version, response_data)

            return ChatResponse(
                answer=answer,
                citations=[],
                session_id=session_id,
                confidence='low',
                max_similarity=max_similarity
            )

        # Step 7: Extract citations
        citations_data = llm_service.extract_citations(answer, chunks)
        citations = [Citation(**c) for c in citations_data]

        # Step 8: Cache full response
        response_data = {
            'answer': answer,
            'citations': citations_data,
            'confidence': 'high',
            'max_similarity': max_similarity
        }
        await cache_service.set_response(question, kb_version, response_data)

        logger.info(f"Successfully generated answer with {len(citations)} citations")

        return ChatResponse(
            answer=answer,
            citations=citations,
            session_id=session_id,
            confidence='high',
            max_similarity=max_similarity
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
