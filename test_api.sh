#!/bin/bash
# Simple API test script for Nova Agent

set -e

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "🧪 Testing Nova Agent API..."
echo ""

# Test 1: Health Check
echo "1️⃣  Testing Health Endpoint..."
HEALTH=$(curl -s "${BASE_URL}/health")
if echo "$HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Health check passed${NC}"
    echo "   Response: $HEALTH"
else
    echo -e "${RED}✗ Health check failed${NC}"
    exit 1
fi
echo ""

# Test 2: Root Endpoint
echo "2️⃣  Testing Root Endpoint..."
ROOT=$(curl -s "${BASE_URL}/")
if echo "$ROOT" | grep -q "Nova Agent"; then
    echo -e "${GREEN}✓ Root endpoint passed${NC}"
else
    echo -e "${RED}✗ Root endpoint failed${NC}"
    exit 1
fi
echo ""

# Test 3: Chat Endpoint
echo "3️⃣  Testing Chat Endpoint..."
CHAT=$(curl -s -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the clinic hours?"}')

if echo "$CHAT" | grep -q "answer"; then
    echo -e "${GREEN}✓ Chat endpoint passed${NC}"
    echo "   Answer preview: $(echo "$CHAT" | python3 -c "import sys, json; print(json.load(sys.stdin)['answer'][:100] + '...')" 2>/dev/null || echo "See full response in demo UI")"
    echo "   Confidence: $(echo "$CHAT" | python3 -c "import sys, json; print(json.load(sys.stdin)['confidence'])" 2>/dev/null || echo "unknown")"
    echo "   Citations: $(echo "$CHAT" | python3 -c "import sys, json; print(len(json.load(sys.stdin)['citations']))" 2>/dev/null || echo "unknown")"
else
    echo -e "${RED}✗ Chat endpoint failed${NC}"
    echo "   Response: $CHAT"
    exit 1
fi
echo ""

# Test 4: Demo UI
echo "4️⃣  Testing Demo UI..."
DEMO=$(curl -s "${BASE_URL}/demo")
if echo "$DEMO" | grep -q "Nova Agent"; then
    echo -e "${GREEN}✓ Demo UI accessible${NC}"
    echo "   Open in browser: ${BASE_URL}/demo"
else
    echo -e "${RED}✗ Demo UI failed${NC}"
    exit 1
fi
echo ""

echo "✅ All API tests passed!"
echo ""
echo "Next steps:"
echo "  • Open demo UI: open ${BASE_URL}/demo"
echo "  • Run full test suite: pytest tests/ -v"
echo "  • View API docs: open ${BASE_URL}/docs"
echo ""
