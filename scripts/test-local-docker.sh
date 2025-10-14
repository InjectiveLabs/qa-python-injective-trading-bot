#!/bin/bash
# Quick test script for local Docker setup

set -e

echo "🧪 Testing Docker Setup Locally..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check Docker is running
echo "1️⃣  Checking Docker..."
if docker ps > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Docker is running${NC}"
else
    echo -e "   ${RED}❌ Docker not running. Please start Docker Desktop${NC}"
    exit 1
fi

# 2. Check .env file exists
echo "2️⃣  Checking .env file..."
if [ -f .env ]; then
    if grep -q "WALLET_1_PRIVATE_KEY" .env && ! grep -q "0x1234567890abcdef" .env; then
        echo -e "   ${GREEN}✅ .env file configured with real keys${NC}"
    elif grep -q "WALLET_1_PRIVATE_KEY" .env; then
        echo -e "   ${YELLOW}⚠️  .env exists but may have template values${NC}"
        echo -e "   ${YELLOW}   Make sure to replace with your actual testnet keys${NC}"
    else
        echo -e "   ${RED}❌ No wallet keys in .env${NC}"
        echo "   Run: cp env.example .env"
        echo "   Then edit .env with your testnet private keys"
        exit 1
    fi
else
    echo -e "   ${RED}❌ .env file not found${NC}"
    echo "   Run: cp env.example .env"
    echo "   Then edit .env with your testnet private keys"
    exit 1
fi

# 3. Check images exist
echo "3️⃣  Checking Docker images..."
if docker images | grep -q "qa-python-injective-trading-bot-web"; then
    echo -e "   ${GREEN}✅ Docker images found${NC}"
else
    echo -e "   ${RED}❌ Images not built${NC}"
    echo "   Run: ./build-images.sh"
    exit 1
fi

# 4. Check if already running
echo "4️⃣  Checking existing containers..."
if docker compose ps | grep -q "trading-bot-web.*Up"; then
    echo -e "   ${YELLOW}⚠️  Dashboard already running${NC}"
    echo "   Skipping startup"
else
    echo "   No containers running, will start dashboard..."
    
    # Start dashboard
    echo "5️⃣  Starting web dashboard..."
    docker compose up -d web
    
    echo "   Waiting for dashboard to start..."
    sleep 5
fi

# 5. Check dashboard is running
echo "6️⃣  Checking dashboard status..."
if docker compose ps | grep -q "trading-bot-web.*Up"; then
    echo -e "   ${GREEN}✅ Dashboard is running${NC}"
else
    echo -e "   ${RED}❌ Dashboard failed to start${NC}"
    echo "   Logs:"
    docker compose logs web
    exit 1
fi

# 6. Check wallets loaded
echo "7️⃣  Checking wallet loading..."
sleep 2
if docker compose logs web | grep -q "Loaded wallet"; then
    WALLET_COUNT=$(docker compose logs web | grep "Loaded wallet" | wc -l | tr -d ' ')
    echo -e "   ${GREEN}✅ ${WALLET_COUNT} wallet(s) loaded successfully${NC}"
    docker compose logs web | grep "Loaded wallet" | sed 's/^/   /'
else
    echo -e "   ${RED}❌ No wallets loaded${NC}"
    echo "   Check your .env file has valid WALLET_*_PRIVATE_KEY entries"
    echo "   Logs:"
    docker compose logs web | tail -20
    exit 1
fi

# 7. Check dashboard accessible
echo "8️⃣  Checking dashboard accessibility..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000 | grep -q "200\|401"; then
    echo -e "   ${GREEN}✅ Dashboard accessible at http://localhost:8000${NC}"
else
    echo -e "   ${RED}❌ Dashboard not accessible${NC}"
    echo "   Check if port 8000 is already in use:"
    echo "   lsof -i :8000"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 All tests passed!${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Next steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. 🌐 Open dashboard in browser:"
echo "   http://localhost:8000"
echo ""
echo "2. 🔐 Login credentials:"
USERNAME=$(grep "WEB_AUTH_USERNAME" .env | cut -d '=' -f2)
echo "   Username: $USERNAME"
echo "   Password: (from your .env file)"
echo ""
echo "3. 🤖 Test starting a bot:"
echo "   - Select a wallet from dropdown"
echo "   - Select a market (e.g., INJ/USDT)"
echo "   - Click 'Start Bot'"
echo "   - Verify bot appears in running bots section"
echo ""
echo "4. 📊 Monitor bot logs:"
echo "   docker compose logs -f"
echo ""
echo "5. 🔍 Check running containers:"
echo "   docker ps | grep bot"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧹 Cleanup commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Stop dashboard:      docker compose down"
echo "View logs:           docker compose logs web"
echo "Restart dashboard:   docker compose restart web"
echo "Remove stopped bots: docker container prune -f"
echo ""

