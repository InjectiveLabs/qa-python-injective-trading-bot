#!/bin/bash
# Run trading bots directly with Docker (without dashboard)

set -e

# Get project directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo "Usage: $0 <bot_type> <wallet_id> <market>"
    echo ""
    echo "Examples:"
    echo "  $0 spot wallet_1 INJ/USDT"
    echo "  $0 derivative wallet_2 INJ/USDT-PERP"
    echo ""
    echo "Bot Types:"
    echo "  spot        - Spot trader"
    echo "  derivative  - Derivative/Perpetual trader"
    echo ""
    exit 1
}

# Check arguments
if [ $# -lt 3 ]; then
    usage
fi

BOT_TYPE=$1
WALLET_ID=$2
MARKET=$3

# Validate bot type
if [ "$BOT_TYPE" != "spot" ] && [ "$BOT_TYPE" != "derivative" ]; then
    echo -e "${RED}❌ Invalid bot type: $BOT_TYPE${NC}"
    usage
fi

# Determine image and container name
if [ "$BOT_TYPE" == "spot" ]; then
    IMAGE_NAME="spot-trader:latest"
    MARKET_ENV="MARKET"
else
    IMAGE_NAME="derivative-trader:latest"
    MARKET_ENV="MARKETS"
fi

CONTAINER_NAME="${BOT_TYPE}-${WALLET_ID}-$(echo $MARKET | tr '/' '-')"

# Check if container already exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}⚠️  Container ${CONTAINER_NAME} already exists${NC}"
    read -p "Remove and recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker rm -f ${CONTAINER_NAME}
    else
        echo "Aborted"
        exit 1
    fi
fi

# Check if image exists
if ! docker images | grep -q "${IMAGE_NAME%:*}"; then
    echo -e "${RED}❌ Docker image not found: $IMAGE_NAME${NC}"
    echo "Run: ./build-images.sh"
    exit 1
fi

# Load wallet private key from .env
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${RED}❌ .env file not found${NC}"
    echo "Create it from: cp env.example .env"
    exit 1
fi

# Source .env to get wallet keys
set -a
source "$PROJECT_ROOT/.env"
set +a

# Get wallet private key variable name
WALLET_KEY_VAR="${WALLET_ID^^}_PRIVATE_KEY"
WALLET_NAME_VAR="${WALLET_ID^^}_NAME"

# Get wallet key value
WALLET_KEY="${!WALLET_KEY_VAR}"

if [ -z "$WALLET_KEY" ]; then
    echo -e "${RED}❌ Wallet private key not found in .env: $WALLET_KEY_VAR${NC}"
    exit 1
fi

echo -e "${GREEN}🚀 Starting ${BOT_TYPE} bot...${NC}"
echo "  Wallet: $WALLET_ID"
echo "  Market: $MARKET"
echo "  Container: $CONTAINER_NAME"
echo ""

# Create network if it doesn't exist
docker network inspect trading-network >/dev/null 2>&1 || docker network create trading-network

# Run container
docker run -d \
  --name "$CONTAINER_NAME" \
  --network trading-network \
  -v "${PROJECT_ROOT}/logs:/app/logs" \
  -v "${PROJECT_ROOT}/config:/app/config:ro" \
  -v "${PROJECT_ROOT}/data:/app/data:ro" \
  -e WALLET_ID="$WALLET_ID" \
  -e ${MARKET_ENV}="$MARKET" \
  -e ${WALLET_KEY_VAR}="$WALLET_KEY" \
  -e ${WALLET_NAME_VAR}="${!WALLET_NAME_VAR}" \
  --restart unless-stopped \
  --label "app=trading-bot" \
  --label "component=bot" \
  --label "wallet_id=$WALLET_ID" \
  --label "market=$MARKET" \
  --label "bot_type=$BOT_TYPE" \
  "$IMAGE_NAME"

# Wait a moment
sleep 2

# Check if container is running
if docker ps | grep -q "$CONTAINER_NAME"; then
    echo -e "${GREEN}✅ Bot started successfully!${NC}"
    echo ""
    echo "📊 View logs:"
    echo "  docker logs -f $CONTAINER_NAME"
    echo ""
    echo "🛑 Stop bot:"
    echo "  docker stop $CONTAINER_NAME"
    echo ""
    echo "🗑️  Remove bot:"
    echo "  docker rm -f $CONTAINER_NAME"
else
    echo -e "${RED}❌ Bot failed to start${NC}"
    echo ""
    echo "View logs:"
    docker logs "$CONTAINER_NAME"
    exit 1
fi

