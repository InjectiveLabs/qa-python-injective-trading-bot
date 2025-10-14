#!/bin/bash
# Manage Docker bots without dashboard

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to list all running bots
list_bots() {
    echo -e "${BLUE}📋 Running Trading Bots:${NC}"
    echo ""
    
    BOTS=$(docker ps --filter "label=app=trading-bot" --filter "label=component=bot" --format "{{.Names}}")
    
    if [ -z "$BOTS" ]; then
        echo "No bots running"
        return
    fi
    
    for bot in $BOTS; do
        STATUS=$(docker inspect -f '{{.State.Status}}' "$bot")
        UPTIME=$(docker inspect -f '{{.State.StartedAt}}' "$bot")
        
        # Get labels
        WALLET=$(docker inspect -f '{{index .Config.Labels "wallet_id"}}' "$bot" 2>/dev/null || echo "unknown")
        MARKET=$(docker inspect -f '{{index .Config.Labels "market"}}' "$bot" 2>/dev/null || echo "unknown")
        TYPE=$(docker inspect -f '{{index .Config.Labels "bot_type"}}' "$bot" 2>/dev/null || echo "unknown")
        
        if [ "$STATUS" == "running" ]; then
            echo -e "${GREEN}✅${NC} $bot"
        else
            echo -e "${RED}❌${NC} $bot"
        fi
        echo "   Wallet: $WALLET | Market: $MARKET | Type: $TYPE"
        echo "   Started: $UPTIME"
        echo ""
    done
}

# Function to stop a bot
stop_bot() {
    local CONTAINER_NAME=$1
    echo -e "${YELLOW}🛑 Stopping bot: $CONTAINER_NAME${NC}"
    docker stop "$CONTAINER_NAME"
    echo -e "${GREEN}✅ Bot stopped${NC}"
}

# Function to remove a bot
remove_bot() {
    local CONTAINER_NAME=$1
    echo -e "${YELLOW}🗑️  Removing bot: $CONTAINER_NAME${NC}"
    docker rm -f "$CONTAINER_NAME"
    echo -e "${GREEN}✅ Bot removed${NC}"
}

# Function to view logs
view_logs() {
    local CONTAINER_NAME=$1
    echo -e "${BLUE}📊 Logs for: $CONTAINER_NAME${NC}"
    echo ""
    docker logs -f "$CONTAINER_NAME"
}

# Function to stop all bots
stop_all() {
    echo -e "${YELLOW}🛑 Stopping all trading bots...${NC}"
    BOTS=$(docker ps --filter "label=app=trading-bot" --filter "label=component=bot" --format "{{.Names}}")
    
    if [ -z "$BOTS" ]; then
        echo "No bots running"
        return
    fi
    
    for bot in $BOTS; do
        docker stop "$bot"
        echo -e "${GREEN}✅${NC} Stopped: $bot"
    done
}

# Function to remove all stopped bots
cleanup() {
    echo -e "${YELLOW}🧹 Cleaning up stopped bot containers...${NC}"
    docker container prune -f --filter "label=app=trading-bot"
    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

# Function to restart a bot
restart_bot() {
    local CONTAINER_NAME=$1
    echo -e "${YELLOW}🔄 Restarting bot: $CONTAINER_NAME${NC}"
    docker restart "$CONTAINER_NAME"
    echo -e "${GREEN}✅ Bot restarted${NC}"
}

# Main menu
case "${1:-}" in
    list)
        list_bots
        ;;
    stop)
        if [ -z "$2" ]; then
            echo "Usage: $0 stop <container_name>"
            exit 1
        fi
        stop_bot "$2"
        ;;
    remove)
        if [ -z "$2" ]; then
            echo "Usage: $0 remove <container_name>"
            exit 1
        fi
        remove_bot "$2"
        ;;
    logs)
        if [ -z "$2" ]; then
            echo "Usage: $0 logs <container_name>"
            exit 1
        fi
        view_logs "$2"
        ;;
    stop-all)
        stop_all
        ;;
    cleanup)
        cleanup
        ;;
    restart)
        if [ -z "$2" ]; then
            echo "Usage: $0 restart <container_name>"
            exit 1
        fi
        restart_bot "$2"
        ;;
    *)
        echo "Trading Bot Management Script"
        echo ""
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  list              - List all running bots"
        echo "  stop <name>       - Stop a specific bot"
        echo "  remove <name>     - Remove a specific bot"
        echo "  logs <name>       - View logs for a specific bot"
        echo "  restart <name>    - Restart a specific bot"
        echo "  stop-all          - Stop all trading bots"
        echo "  cleanup           - Remove all stopped bot containers"
        echo ""
        echo "Examples:"
        echo "  $0 list"
        echo "  $0 stop spot-wallet_1-INJ-USDT"
        echo "  $0 logs spot-wallet_1-INJ-USDT"
        echo "  $0 stop-all"
        echo ""
        exit 1
        ;;
esac

