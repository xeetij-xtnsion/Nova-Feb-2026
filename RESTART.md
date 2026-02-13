# Quick Restart Guide

## 🚀 To Resume Your Work Later

### 1. Start Docker Containers
```bash
docker compose up -d
```

Wait for containers to be healthy (~10 seconds)

### 2. Activate Python Environment
```bash
source venv/bin/activate
```

### 3. Start the API Server
```bash
# Make sure DATABASE_URL env var is not set (to use .env file)
unset DATABASE_URL

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or run in background:
```bash
unset DATABASE_URL && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

### 4. Access the Demo
```bash
open http://localhost:8000/demo
```

## 📝 Quick Health Check

```bash
# Check Docker containers
docker compose ps

# Check server
curl http://localhost:8000/health

# Check database has chunks
docker compose exec postgres psql -U postgres -d nova_agent -c "SELECT COUNT(*) FROM kb_chunks;"
```

## 🛑 To Stop Everything

```bash
# Stop API server
pkill -f "uvicorn app.main:app"

# Stop Docker containers (keeps data)
docker compose stop

# Or stop and remove everything
docker compose down
```

## 📊 System Status at Save

- ✅ **330 chunks** ingested from nova_clinic_kb.docx
- ✅ **Database**: PostgreSQL with pgvector extension
- ✅ **Cache**: Redis for retrieval + response caching
- ✅ **Model**: Claude 3 Haiku (patient-friendly responses)
- ✅ **Threshold**: 0.6 similarity for confidence
- ✅ **UI**: Demo with quick action buttons at /demo

## 🔧 Troubleshooting

**If ingestion is needed again:**
```bash
source venv/bin/activate
unset DATABASE_URL
python scripts/ingest_kb.py
```

**If database needs reset:**
```bash
docker compose down -v  # Removes volumes
docker compose up -d
source venv/bin/activate
unset DATABASE_URL
python scripts/ingest_kb.py
```

**Check logs:**
```bash
# Docker logs
docker compose logs -f postgres
docker compose logs -f redis

# Server logs (if running in background)
tail -f server.log
```

## 💡 Key Files Modified

- **app/config.py** - Similarity threshold: 0.6, Model: claude-3-haiku-20240307
- **app/services/llm.py** - Conversational prompt for patient-friendly responses
- **app/routers/demo.py** - Enhanced UI with quick action buttons
- **.env** - DATABASE_URL set to nova_agent database

## 📦 What's Saved

Your Docker volumes persist:
- PostgreSQL data (330 chunks)
- Redis cache (will be empty on restart)

Your .env file has all API keys configured.
