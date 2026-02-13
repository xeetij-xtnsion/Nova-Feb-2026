#!/bin/bash
# Setup diagnostics for Nova Agent

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🔍 Nova Agent Setup Diagnostics"
echo "================================"
echo ""

# Check 1: Docker
echo -n "1. Docker installed: "
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Yes${NC}"

    echo -n "   Docker running: "
    if docker ps &> /dev/null; then
        echo -e "${GREEN}✓ Yes${NC}"
    else
        echo -e "${RED}✗ No - Please start Docker Desktop${NC}"
    fi
else
    echo -e "${RED}✗ Not installed${NC}"
    echo -e "   ${YELLOW}→ Install from: https://www.docker.com/products/docker-desktop/${NC}"
fi
echo ""

# Check 2: Docker Compose
echo -n "2. Containers running: "
if docker compose ps 2>/dev/null | grep -q "Up"; then
    echo -e "${GREEN}✓ Yes${NC}"
    docker compose ps
else
    echo -e "${RED}✗ No${NC}"
    echo -e "   ${YELLOW}→ Run: docker compose up -d${NC}"
fi
echo ""

# Check 3: PostgreSQL
echo -n "3. PostgreSQL tools: "
if command -v pg_config &> /dev/null; then
    echo -e "${GREEN}✓ Installed${NC}"
else
    echo -e "${RED}✗ Not installed${NC}"
    echo -e "   ${YELLOW}→ Run: brew install postgresql@16${NC}"
fi
echo ""

# Check 4: Virtual Environment
echo -n "4. Virtual environment: "
if [ -d "venv" ]; then
    echo -e "${GREEN}✓ Created${NC}"

    echo -n "   Dependencies installed: "
    if [ -f "venv/bin/uvicorn" ]; then
        echo -e "${GREEN}✓ Yes${NC}"
    else
        echo -e "${RED}✗ No${NC}"
        echo -e "   ${YELLOW}→ Run: source venv/bin/activate && pip install -r requirements.txt${NC}"
    fi
else
    echo -e "${RED}✗ Not created${NC}"
    echo -e "   ${YELLOW}→ Run: python3 -m venv venv${NC}"
fi
echo ""

# Check 5: .env file
echo -n "5. Configuration (.env): "
if [ -f ".env" ]; then
    echo -e "${GREEN}✓ Exists${NC}"
    if grep -q "ANTHROPIC_API_KEY" .env && grep -q "OPENAI_API_KEY" .env; then
        echo -e "   ${GREEN}✓ API keys configured${NC}"
    else
        echo -e "   ${YELLOW}⚠ API keys missing${NC}"
    fi
else
    echo -e "${RED}✗ Missing${NC}"
fi
echo ""

# Check 6: Knowledge Base
echo -n "6. Knowledge base file: "
if [ -f "kb/sources/nova_clinic_kb.docx" ]; then
    SIZE=$(ls -lh kb/sources/nova_clinic_kb.docx | awk '{print $5}')
    echo -e "${GREEN}✓ Found ($SIZE)${NC}"
else
    echo -e "${RED}✗ Not found${NC}"
fi
echo ""

# Check 7: Server running
echo -n "7. API server: "
if lsof -i :8000 &> /dev/null; then
    echo -e "${GREEN}✓ Running on port 8000${NC}"
    echo -e "   ${GREEN}→ Demo UI: http://localhost:8000/demo${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo -e "   ${YELLOW}→ Run: source venv/bin/activate && uvicorn app.main:app --reload${NC}"
fi
echo ""

echo "================================"
echo ""

# Summary
ISSUES=0
command -v docker &> /dev/null || ((ISSUES++))
docker compose ps 2>/dev/null | grep -q "Up" || ((ISSUES++))
[ -f "venv/bin/uvicorn" ] || ((ISSUES++))
lsof -i :8000 &> /dev/null || ((ISSUES++))

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ Everything looks good! Open http://localhost:8000/demo${NC}"
else
    echo -e "${YELLOW}⚠️  Found $ISSUES issue(s). Follow the suggestions above.${NC}"
    echo ""
    echo "Quick fix commands:"
    echo "  1. Start Docker Desktop (from Applications)"
    echo "  2. docker compose up -d"
    echo "  3. source venv/bin/activate && pip install -r requirements.txt"
    echo "  4. python scripts/ingest_kb.py"
    echo "  5. uvicorn app.main:app --reload"
fi
echo ""
