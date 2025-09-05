# 🏗️ QA Injective MM Bot - System Architecture

## 🎯 Overview

The QA Injective MM Bot is a sophisticated market making system that operates on Injective Protocol's testnet while using mainnet prices as reference. The system consists of a trading engine and a modern web dashboard for monitoring and control.

## 🏗️ System Components

### 🤖 Trading Engine
- **Multi-Wallet Trader**: Core trading logic with parallel wallet execution
- **Price Correction Logic**: Compares testnet vs mainnet prices and places correction orders
- **Rich Orderbook Creation**: Places randomized orders to create natural-looking orderbooks
- **Sequence Management**: Handles blockchain sequence numbers and prevents conflicts

### 🌐 Web Dashboard
- **FastAPI Backend**: REST API and WebSocket server for real-time communication
- **Modern Frontend**: HTML5, Tailwind CSS, and vanilla JavaScript
- **Real-time Updates**: WebSocket-based live data streaming
- **Bot Control Interface**: Start/stop functionality with status monitoring

## 🔄 Data Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   🌐 Web        │    │   🤖 Trading    │    │   🧪 Injective  │
│   Dashboard     │    │   Engine        │    │   Testnet       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ WebSocket             │                       │
         │ Real-time Updates     │                       │
         ├──────────────────────►│                       │
         │                       │                       │
         │                       │ Trading Orders        │
         │                       ├──────────────────────►│
         │                       │                       │
         │                       │ Price Data            │
         │                       │◄──────────────────────┤
         │                       │                       │
         │                       │                       │
         │                       │                       │
┌─────────────────┐              │                       │
│   🌐 Injective  │              │                       │
│   Mainnet       │              │                       │
└─────────────────┘              │                       │
         │                       │                       │
         │ Price Reference       │                       │
         ├──────────────────────►│                       │
         │                       │                       │
```

## 🎯 Trading Logic

### Price Correction Algorithm
1. **Fetch Prices**: Get current prices from both testnet and mainnet
2. **Calculate Difference**: Determine percentage difference between prices
3. **Decision Logic**: If difference > threshold (2%), place correction orders
4. **Order Placement**: Create randomized orders to correct price discrepancy
5. **Wait & Repeat**: 10-second cycle before next price check

### Multi-Wallet Coordination
- **Parallel Execution**: All wallets trade simultaneously
- **Market Coverage**: Each wallet trades all configured markets
- **Load Distribution**: Orders spread across multiple wallets
- **Risk Management**: Individual wallet limits and cooldowns

## 🔧 Technical Architecture

### Backend Services
```
┌─────────────────────────────────────────────────────────┐
│                    🚀 FastAPI Server                   │
├─────────────────────────────────────────────────────────┤
│  📡 REST API Endpoints                                 │
│  ├── GET  /api/status     - Bot status & system info   │
│  ├── GET  /api/balances   - Wallet balance data        │
│  ├── POST /api/control    - Start/stop bot commands    │
│  └── GET  /api/logs       - Trading log data           │
│                                                         │
│  ⚡ WebSocket Server                                     │
│  ├── Real-time status updates                          │
│  ├── Live balance streaming                            │
│  ├── Trading event notifications                       │
│  └── System health monitoring                          │
│                                                         │
│  🎛️ Bot Control Interface                               │
│  ├── Process management                                │
│  ├── Configuration loading                             │
│  ├── Log file monitoring                               │
│  └── Error handling & recovery                         │
└─────────────────────────────────────────────────────────┘
```

### Frontend Components
```
┌─────────────────────────────────────────────────────────┐
│                    📱 Web Interface                    │
├─────────────────────────────────────────────────────────┤
│  🎨 UI Components                                       │
│  ├── Bot Status Panel     - Running/Stopped indicator  │
│  ├── Wallet Balances      - Real-time balance display  │
│  ├── Market Information   - Trading pairs & status     │
│  ├── Activity Feed        - Live trading logs          │
│  └── Control Buttons      - Start/stop functionality   │
│                                                         │
│  ⚡ Real-time Features                                   │
│  ├── WebSocket client     - Live data connection       │
│  ├── Auto-refresh         - Periodic data updates      │
│  ├── Status indicators    - Visual feedback system     │
│  └── Error handling       - User-friendly error msgs   │
│                                                         │
│  📱 Responsive Design                                    │
│  ├── Mobile-first         - Touch-friendly interface   │
│  ├── Adaptive layout      - Works on all screen sizes  │
│  ├── Modern styling       - Tailwind CSS framework     │
│  └── Accessibility        - WCAG compliant design      │
└─────────────────────────────────────────────────────────┘
```

## 🔒 Security & Risk Management

### Data Protection
- **Private Key Security**: Keys stored in environment variables, never transmitted
- **API Security**: Input validation and sanitization on all endpoints
- **Network Security**: Localhost-only access by default
- **Log Security**: Sensitive data filtered from logs

### Risk Controls
- **Sequence Management**: Automatic sequence number synchronization
- **Cooldown Periods**: 10-second delays on sequence mismatches
- **Order Limits**: Configurable maximum orders per wallet
- **Balance Monitoring**: Real-time balance tracking and alerts

## 📊 Performance Characteristics

### Scalability
- **Multi-threaded**: Parallel wallet execution
- **Async Operations**: Non-blocking I/O operations
- **Efficient APIs**: Fast response times with caching
- **Resource Management**: Low memory and CPU footprint

### Reliability
- **Error Recovery**: Automatic retry mechanisms
- **Graceful Shutdown**: Clean process termination
- **Logging**: Comprehensive audit trail
- **Health Monitoring**: Real-time system status

## 🚀 Deployment Architecture

### Development Environment
```
┌─────────────────┐    ┌─────────────────┐
│   💻 Developer  │    │   🖥️ Local      │
│   Machine       │    │   Server        │
└─────────────────┘    └─────────────────┘
         │                       │
         │ SSH/HTTP              │
         ├──────────────────────►│
         │                       │
         │                       │
         │                       ▼
         │              ┌─────────────────┐
         │              │   🤖 Trading    │
         │              │   Bot Process   │
         │              └─────────────────┘
         │                       │
         │                       │
         │                       ▼
         │              ┌─────────────────┐
         │              │   🧪 Injective  │
         │              │   Testnet       │
         │              └─────────────────┘
```

### Production Considerations
- **Process Management**: Use systemd or PM2 for process supervision
- **Log Rotation**: Implement log rotation to prevent disk space issues
- **Monitoring**: Set up health checks and alerting
- **Backup**: Regular configuration and log backups
- **Security**: Firewall rules and access controls

## 🔮 Future Enhancements

### Planned Features
- **Advanced Analytics**: Performance metrics and P&L tracking
- **Strategy Configuration**: Web-based parameter adjustment
- **Multi-Market Support**: Additional trading pairs and markets
- **Risk Management**: Position limits and stop-loss mechanisms
- **Mobile App**: Native mobile application

### Technical Improvements
- **Database Integration**: Persistent data storage
- **Microservices**: Service-oriented architecture
- **Containerization**: Docker deployment support
- **Load Balancing**: Multiple instance support
- **API Versioning**: Backward compatibility management

---

**Architecture designed for scalability, reliability, and maintainability**

*This architecture supports both development and production environments with comprehensive monitoring, control, and risk management capabilities.*
