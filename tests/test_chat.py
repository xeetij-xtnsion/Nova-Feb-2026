import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_chat_success(client: AsyncClient):
    """Test successful chat response with mocked services."""

    # Mock embedding service
    mock_embedding = [0.1] * 1536

    # Mock retrieval results
    mock_chunks = [
        {
            'chunk_id': 'test-chunk-1',
            'source_file': 'test.docx',
            'section_heading': 'Test Section',
            'content': 'This is test content about clinic hours.',
            'chunk_index': 0,
            'similarity': 0.85
        }
    ]

    mock_retrieval_result = {
        'chunks': mock_chunks,
        'is_confident': True,
        'max_similarity': 0.85
    }

    # Mock LLM response
    mock_answer = "The clinic is open Monday to Friday from 9 AM to 5 PM. [test-chunk-1]"

    with patch('app.routers.chat.embedding_service') as mock_emb_service, \
         patch('app.routers.chat.retrieve_with_confidence') as mock_retrieve, \
         patch('app.routers.chat.llm_service') as mock_llm_service:

        # Configure mocks
        mock_emb_service.embed_text = AsyncMock(return_value=mock_embedding)
        mock_retrieve.return_value = mock_retrieval_result

        mock_llm_service.generate_answer = AsyncMock(return_value=mock_answer)
        mock_llm_service.extract_citations = MagicMock(return_value=[
            {
                'chunk_id': 'test-chunk-1',
                'source_file': 'test.docx',
                'section_heading': 'Test Section',
                'chunk_index': 0
            }
        ])

        # Make request
        response = await client.post(
            "/chat",
            json={"message": "What are the clinic hours?"}
        )

        assert response.status_code == 200

        data = response.json()
        assert "answer" in data
        assert data["confidence"] == "high"
        assert len(data["citations"]) > 0
        assert data["citations"][0]["chunk_id"] == "test-chunk-1"


@pytest.mark.asyncio
async def test_chat_low_confidence(client: AsyncClient):
    """Test chat response with low confidence retrieval."""

    # Mock embedding service
    mock_embedding = [0.1] * 1536

    # Mock low confidence retrieval
    mock_retrieval_result = {
        'chunks': [],
        'is_confident': False,
        'max_similarity': 0.3
    }

    with patch('app.routers.chat.embedding_service') as mock_emb_service, \
         patch('app.routers.chat.retrieve_with_confidence') as mock_retrieve:

        # Configure mocks
        mock_emb_service.embed_text = AsyncMock(return_value=mock_embedding)
        mock_retrieve.return_value = mock_retrieval_result

        # Make request
        response = await client.post(
            "/chat",
            json={"message": "What is the meaning of life?"}
        )

        assert response.status_code == 200

        data = response.json()
        assert data["confidence"] == "low"
        assert "don't have sufficient information" in data["answer"].lower()
        assert len(data["citations"]) == 0


@pytest.mark.asyncio
async def test_chat_empty_message(client: AsyncClient):
    """Test chat with empty message."""
    response = await client.post(
        "/chat",
        json={"message": ""}
    )

    # Should return validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_with_session_id(client: AsyncClient):
    """Test chat with session ID."""

    mock_embedding = [0.1] * 1536

    mock_retrieval_result = {
        'chunks': [{
            'chunk_id': 'test-chunk-1',
            'source_file': 'test.docx',
            'section_heading': 'Test',
            'content': 'Test content',
            'chunk_index': 0,
            'similarity': 0.85
        }],
        'is_confident': True,
        'max_similarity': 0.85
    }

    mock_answer = "Test answer [test-chunk-1]"

    with patch('app.routers.chat.embedding_service') as mock_emb_service, \
         patch('app.routers.chat.retrieve_with_confidence') as mock_retrieve, \
         patch('app.routers.chat.llm_service') as mock_llm_service:

        mock_emb_service.embed_text = AsyncMock(return_value=mock_embedding)
        mock_retrieve.return_value = mock_retrieval_result
        mock_llm_service.generate_answer = AsyncMock(return_value=mock_answer)
        mock_llm_service.extract_citations = MagicMock(return_value=[])

        # Make request with session ID
        session_id = "test-session-123"
        response = await client.post(
            "/chat",
            json={"message": "Test question", "session_id": session_id}
        )

        assert response.status_code == 200

        data = response.json()
        assert data["session_id"] == session_id
