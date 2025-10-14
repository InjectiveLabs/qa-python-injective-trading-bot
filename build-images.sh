#!/bin/bash
# Build all Docker images for trading bot system

set -e  # Exit on error

echo "🐳 Building Trading Bot Docker Images..."
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    exit 1
fi

# Check if docker compose is available
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed!"
    exit 1
fi

echo "✅ Docker detected: $(docker --version)"
echo "✅ Docker Compose detected: $(docker compose version)"
echo ""

# Build all images
echo "📦 Building images (this may take 3-5 minutes)..."
echo ""

# Build web dashboard
echo "🌐 Building web dashboard..."
docker compose build web

echo ""
echo "🤖 Building spot trader..."
docker build -t spot-trader:latest -f docker/spot-trader/Dockerfile .

echo ""
echo "📊 Building derivative trader..."
docker build -t derivative-trader:latest -f docker/derivative-trader/Dockerfile .

echo ""
echo "✅ Build complete!"
echo ""

# Show built images
echo "📋 Built images:"
docker images | grep -E 'REPOSITORY|injective-testnet-liquidity-bot|spot-trader|derivative-trader'

echo ""
echo "🎉 Ready to deploy!"
echo ""
echo "Next steps:"
echo "  1. Configure .env file with wallet keys"
echo "  2. Start web dashboard: docker compose up -d web"
echo "  3. Access dashboard: http://localhost:8000"
echo ""

