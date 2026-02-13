# Quick Setup Guide for Nova Agent

## Prerequisites Setup

### 1. Install Docker Desktop (if not already installed)
Download and install Docker Desktop for Mac:
https://www.docker.com/products/docker-desktop/

### 2. Install PostgreSQL (needed for Python package compilation)
```bash
brew install postgresql@16
```

## Setup Steps

### Step 1: Start Infrastructure
```bash
# Start PostgreSQL and Redis containers
docker compose up -d

# Verify containers are running
docker compose ps
```

### Step 2: Set Up Python Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Run Knowledge Base Ingestion
```bash
# Make sure venv is activated
source venv/bin/activate

# Run ingestion
python scripts/ingest_kb.py
```

Expected output:
```
INFO - Initializing database...
INFO - ✓ Database initialized
INFO - Found 1 .docx file(s)
INFO - Processing nova_clinic_kb.docx...
INFO - Parsed X sections from nova_clinic_kb.docx
INFO - Created XX chunks from nova_clinic_kb.docx
INFO - Embedding batch 1/1
INFO - ✓ Ingested XX chunks from nova_clinic_kb.docx
INFO - ✓ Ingestion complete! Total chunks: XX
```

### Step 4: Start API Server
```bash
# In a new terminal, activate venv
source venv/bin/activate

# Start server
uvicorn app.main:app --reload
```

Server will start at: `http://localhost:8000`

### Step 5: Test the System

#### A. Health Check
```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status":"healthy","service":"nova-agent"}
```

#### B. Chat Endpoint
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the clinic hours?"}'
```

#### C. Demo UI
Open in browser: `http://localhost:8000/demo`

#### D. Run Tests
```bash
# In terminal with venv activated
pytest tests/ -v
```

## Quick Commands Reference

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Activate venv (run from project root)
source venv/bin/activate

# Start API server
uvicorn app.main:app --reload

# Run tests
pytest tests/ -v

# Run ingestion
python scripts/ingest_kb.py
```

## Troubleshooting

### "docker: command not found"
- Install Docker Desktop and make sure it's running

### "pg_config executable not found"
- Install PostgreSQL: `brew install postgresql@16`

### Database connection errors
- Make sure Docker containers are running: `docker compose ps`
- Check logs: `docker compose logs postgres`

### Redis connection fails
- System will continue without caching (warning in logs)
- Check Redis: `docker compose logs redis`

### Port 8000 already in use
- Find process: `lsof -ti:8000`
- Kill it: `kill -9 $(lsof -ti:8000)`
- Or use different port: `uvicorn app.main:app --port 8001`

## Next Steps After Setup

1. Try asking questions in the demo UI
2. Check the feedback functionality (thumbs up/down)
3. Monitor the logs to see the RAG pipeline in action
4. Experiment with different questions to test confidence scoring
5. Check Redis cache hits in the logs

## Architecture Overview

When you send a chat request:
1. ✅ Response cache check (30min TTL)
2. 🔢 Query embedding (OpenAI)
3. ✅ Retrieval cache check (1hr TTL)
4. 🔍 Vector search (PostgreSQL + pgvector)
5. 📊 Confidence assessment (similarity threshold)
6. 🤖 Answer generation (Claude)
7. 📚 Citation extraction
8. 💾 Cache results
9. ✨ Return response

Happy testing! 🚀
