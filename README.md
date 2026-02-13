# Nova Agent - RAG MVP

A production-ready RAG (Retrieval Augmented Generation) system for Nova Clinic that ingests medical documentation, creates vector embeddings, and answers questions using Claude AI with source citations.

## Features

- 📚 **Document Ingestion**: Parse .docx files with section-aware chunking
- 🔍 **Vector Search**: PostgreSQL + pgvector with HNSW indexing
- 🤖 **AI-Powered Answers**: Claude 3.5 Sonnet for response generation
- 📝 **Source Citations**: Automatic citation extraction with metadata
- ⚡ **Two-Tier Caching**: Redis caching for retrieval and responses
- 🎯 **Confidence Detection**: Hybrid approach using similarity + LLM signals
- 👍 **User Feedback**: Thumbs up/down rating system
- 🎨 **Demo UI**: Beautiful web interface for testing

## Architecture

**Tech Stack:**
- **FastAPI** - Async web framework
- **OpenAI** - text-embedding-3-small (1536 dimensions)
- **Anthropic** - Claude 3.5 Sonnet
- **PostgreSQL** - pgvector with HNSW index
- **Redis** - Retrieval + response caching
- **python-docx** - Document parsing

**Core Design:**
1. Section-aware chunking preserves document structure
2. Hybrid confidence detection (cosine similarity + LLM signal)
3. Two-tier caching with kb_version keys for auto-invalidation
4. Citations extracted from [chunk_id] references
5. Stateless sessions (client-provided session_id for feedback grouping)

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- OpenAI API key
- Anthropic API key
- PostgreSQL database
- Redis (optional, for caching)

## Quick Start

### 1. Clone and Configure

```bash
git clone <repository-url>
cd nova-agent

# Create .env file with your configuration
cat > .env << EOF
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nova_agent
REDIS_URL=redis://localhost:6379/0
CHUNK_SIZE=700
CHUNK_OVERLAP=120
TOP_K=8
KB_VERSION=1
EOF
```

### 2. Start Infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL (with pgvector) and Redis containers.

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Knowledge Base Ingestion

```bash
python scripts/ingest_kb.py
```

This will:
- Parse all .docx files in `kb/sources/`
- Create section-aware chunks
- Generate OpenAI embeddings
- Store in PostgreSQL with vector index

Example output:
```
INFO - Processing nova_clinic_kb.docx...
INFO - Created 45 chunks from nova_clinic_kb.docx
INFO - Embedding batch 1/1
INFO - ✓ Ingested 45 chunks from nova_clinic_kb.docx
INFO - ✓ Ingestion complete! Total chunks: 45
```

### 5. Start API Server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

### 6. Test the System

#### Health Check
```bash
curl http://localhost:8000/health
```

#### Chat API
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the clinic hours?"}'
```

#### Demo UI
Open `http://localhost:8000/demo` in your browser for an interactive chat interface.

## API Endpoints

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "nova-agent"
}
```

### POST /chat
Main RAG chat endpoint.

**Request:**
```json
{
  "message": "What are the clinic hours?",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "answer": "Nova Clinic is open Monday to Friday from 9 AM to 5 PM. [chunk-id]",
  "citations": [
    {
      "chunk_id": "uuid-here",
      "source_file": "nova_clinic_kb.docx",
      "section_heading": "Operating Hours",
      "chunk_index": 3
    }
  ],
  "session_id": "optional-session-id",
  "confidence": "high",
  "max_similarity": 0.87
}
```

### POST /ingest
Trigger knowledge base ingestion (can run in background).

**Request:**
```json
{
  "sources_dir": "kb/sources",
  "kb_version": 1,
  "background": false
}
```

**Response:**
```json
{
  "status": "completed",
  "message": "Ingestion completed successfully from kb/sources"
}
```

### POST /feedback
Submit user feedback on responses.

**Request:**
```json
{
  "session_id": "optional-session-id",
  "question": "What are the clinic hours?",
  "answer": "Nova Clinic is open...",
  "citations": [...],
  "rating": 1
}
```

`rating`: 1 for thumbs up, -1 for thumbs down

**Response:**
```json
{
  "status": "success",
  "message": "Thank you for your feedback!"
}
```

### GET /demo
Returns interactive HTML demo UI.

## Project Structure

```
nova-agent/
├── docker-compose.yml           # Postgres + Redis infrastructure
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── .env                         # Environment configuration
├── scripts/
│   └── ingest_kb.py            # CLI ingestion script
├── app/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Environment configuration
│   ├── database.py             # Database session management
│   ├── redis_client.py         # Redis client singleton
│   ├── models/
│   │   └── database.py         # SQLAlchemy models
│   ├── schemas/
│   │   ├── chat.py             # Chat request/response schemas
│   │   └── feedback.py         # Feedback schemas
│   ├── routers/
│   │   ├── health.py           # Health check
│   │   ├── chat.py             # Chat endpoint
│   │   ├── ingest.py           # Ingestion endpoint
│   │   ├── feedback.py         # Feedback endpoint
│   │   └── demo.py             # Demo UI
│   ├── services/
│   │   ├── embedding.py        # OpenAI embedding service
│   │   ├── chunking.py         # Document chunking
│   │   ├── retrieval.py        # Vector similarity search
│   │   ├── llm.py              # Claude API service
│   │   └── cache.py            # Redis caching
│   └── utils/
│       └── docx_parser.py      # .docx parser
└── tests/
    ├── conftest.py             # Pytest fixtures
    ├── test_health.py          # Health tests
    └── test_chat.py            # Chat tests
```

## Database Schema

### kb_chunks table
- `id` - Serial primary key
- `chunk_id` - UUID for stable references
- `source_file` - Source document name
- `section_heading` - Document heading
- `chunk_index` - Sequential position
- `content` - Chunk text
- `embedding` - Vector(1536) with HNSW index
- `kb_version` - Version for cache invalidation
- `created_at` - Timestamp

### feedback table
- `id` - Serial primary key
- `session_id` - Optional session identifier
- `question` - User's question
- `answer` - Generated answer
- `citations` - JSONB array of citations
- `rating` - 1 (thumbs up) or -1 (thumbs down)
- `created_at` - Timestamp

## RAG Pipeline

The chat endpoint implements a sophisticated RAG pipeline:

1. **Response Cache Check** - Fast path for repeated queries
2. **Query Embedding** - OpenAI text-embedding-3-small
3. **Retrieval Cache Check** - Cached vector search results
4. **Vector Search** - pgvector cosine similarity with HNSW index
5. **Confidence Assessment** - Threshold check (0.7) on max similarity
6. **Answer Generation** - Claude 3.5 Sonnet with context
7. **Citation Extraction** - Parse [chunk_id] references
8. **Cache Storage** - Store retrieval + response
9. **Return Response** - With citations and confidence level

## Confidence Detection

**Two-Level Approach:**
- **Retrieval Confidence**: Max cosine similarity >= 0.7
- **LLM Confidence**: Claude doesn't respond with "KB_INSUFFICIENT_INFO"

**Low Confidence Response:**
```
"I apologize, but I don't have sufficient information in my knowledge
base to answer your question accurately. Could you please rephrase your
question or ask something else about Nova Clinic's services, hours, or
policies?"
```

## Caching Strategy

**Two-Tier Cache:**
- **Retrieval Cache**: 1 hour TTL, stores vector search results
  - Key: `retrieval:v{kb_version}:k{top_k}:h{embedding_hash}`
- **Response Cache**: 30 minutes TTL, stores full responses
  - Key: `response:v{kb_version}:h{text_hash}`

**Benefits:**
- Reduces OpenAI/Anthropic API costs
- Improves response times
- Auto-invalidates when KB version changes
- Graceful degradation if Redis unavailable

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

Tests include:
- Health check endpoint
- Chat endpoint with mocked services
- Low confidence handling
- Session ID handling
- Input validation

## Configuration

All configuration is done via environment variables (`.env` file):

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `DATABASE_URL` | PostgreSQL connection URL | Required |
| `REDIS_URL` | Redis connection URL | Required |
| `CHUNK_SIZE` | Maximum chunk size in characters | 700 |
| `CHUNK_OVERLAP` | Overlap between chunks | 120 |
| `TOP_K` | Number of chunks to retrieve | 8 |
| `KB_VERSION` | Knowledge base version | 1 |

## Development

### Adding New Documents

1. Place .docx files in `kb/sources/`
2. Run ingestion: `python scripts/ingest_kb.py`
3. Optionally increment `KB_VERSION` in `.env` to invalidate caches

### Updating Configuration

Edit `.env` file and restart the server.

### Monitoring

Logs are written to stdout with structured logging:
```
2024-01-15 10:30:45 - app.routers.chat - INFO - Processing query: What are the clinic hours?
2024-01-15 10:30:46 - app.routers.chat - INFO - Retrieved 8 chunks, max_similarity=0.850, confident=True
2024-01-15 10:30:47 - app.routers.chat - INFO - Successfully generated answer with 2 citations
```

## Production Considerations

1. **Security**
   - Set specific CORS origins in production
   - Use environment variable management (e.g., AWS Secrets Manager)
   - Enable HTTPS/TLS
   - Add authentication/authorization

2. **Scalability**
   - Use connection pooling for PostgreSQL
   - Consider Redis Cluster for high availability
   - Deploy multiple API instances behind load balancer
   - Monitor OpenAI/Anthropic rate limits

3. **Monitoring**
   - Add application metrics (Prometheus/Grafana)
   - Set up error tracking (Sentry)
   - Monitor API usage and costs
   - Track feedback ratings and confidence scores

4. **Database**
   - Regular backups of PostgreSQL
   - Monitor vector index performance
   - Tune HNSW parameters for your dataset

## Troubleshooting

**Database connection fails:**
```bash
# Check PostgreSQL is running
docker compose ps

# Check logs
docker compose logs postgres
```

**Redis connection fails:**
System continues without caching. Check Redis logs:
```bash
docker compose logs redis
```

**Ingestion fails:**
- Verify .docx files exist in `kb/sources/`
- Check OpenAI API key is valid
- Ensure database is initialized

**Low confidence responses:**
- Check similarity scores in logs
- Consider adjusting `SIMILARITY_THRESHOLD`
- Ensure KB contains relevant information
- Try different chunking parameters

## License

[Your License Here]

## Support

For issues and questions, please open a GitHub issue.
