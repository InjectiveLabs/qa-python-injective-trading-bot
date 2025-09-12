/**
 * Injective Trading Bot Dashboard - Frontend JavaScript
 * Handles real-time updates, bot control, and UI interactions
 */

class TradingBotDashboard {
    constructor() {
        this.ws = null;
        this.isConnected = false;
        this.balanceRefreshInterval = null;
        this.botRunning = false;
        this.lastLogs = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.connectWebSocket();
        this.loadInitialData();
    }

    setupEventListeners() {
        // Bot control buttons
        document.getElementById('start-btn').addEventListener('click', () => this.controlBot('start'));
        document.getElementById('stop-btn').addEventListener('click', () => this.controlBot('stop'));
        
        // Balance toggle button
        document.getElementById('toggle-balances').addEventListener('click', () => this.toggleBalanceDetails());
        
        // Log refresh button
        document.getElementById('refresh-logs').addEventListener('click', () => this.refreshLogs());
        
        // Full logs button
        document.getElementById('view-full-logs').addEventListener('click', () => this.viewFullLogs());
        
        // Modal controls
        document.getElementById('close-log-modal').addEventListener('click', () => this.closeLogModal());
        document.getElementById('refresh-full-logs').addEventListener('click', () => this.refreshFullLogs());
        
        // Close modal when clicking outside
        document.getElementById('log-modal').addEventListener('click', (e) => {
            if (e.target.id === 'log-modal') {
                this.closeLogModal();
            }
        });
        
        // Balance refresh button
        document.getElementById('refresh-balances').addEventListener('click', () => this.refreshBalances());
        
        // Orders refresh button
        document.getElementById('refresh-orders').addEventListener('click', () => this.refreshOrders());
    }

    async loadInitialData() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            this.updateUI(data);
            
            // Load balance and orders data
            await this.loadBalances();
            await this.refreshOrders();
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.showError('Failed to load dashboard data');
        }
    }

    async loadBalances() {
        try {
            const response = await fetch('/api/balances');
            const data = await response.json();
            this.updateBalances(data);
        } catch (error) {
            console.error('Failed to load balances:', error);
            this.updateBalances({ error: 'Failed to load wallet balances' });
        }
    }

    async refreshBalances() {
        const refreshBtn = document.getElementById('refresh-balances');
        const refreshText = document.getElementById('refresh-text');
        
        // Show loading state
        refreshBtn.disabled = true;
        refreshText.textContent = 'Refreshing...';
        
        try {
            await this.loadBalances();
        } finally {
            // Reset button state
            refreshBtn.disabled = false;
            refreshText.textContent = 'Refresh';
        }
    }

    startBalanceAutoRefresh() {
        // Clear any existing interval
        this.stopBalanceAutoRefresh();
        
        // Start auto-refresh every 30 seconds
        this.balanceRefreshInterval = setInterval(() => {
            this.loadBalances();
        }, 30000);
        
        console.log('Started automatic balance refresh (30s interval)');
    }

    stopBalanceAutoRefresh() {
        if (this.balanceRefreshInterval) {
            clearInterval(this.balanceRefreshInterval);
            this.balanceRefreshInterval = null;
            console.log('Stopped automatic balance refresh');
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            this.isConnected = true;
            console.log('✅ WebSocket connected successfully');
            this.updateWebSocketStatus(true);
            
            // Test the connection by requesting initial data
            this.loadInitialData();
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('📡 WebSocket message received:', {
                    botRunning: data.bot?.running,
                    timestamp: data.websocket_timestamp,
                    hasBotData: !!data.bot
                });
                this.updateUI(data);
            } catch (error) {
                console.error('❌ Failed to process WebSocket message:', error);
                // Don't let WebSocket errors crash the connection
            }
        };
        
        this.ws.onclose = () => {
            this.isConnected = false;
            console.log('❌ WebSocket disconnected, attempting to reconnect...');
            this.updateWebSocketStatus(false);
            setTimeout(() => this.connectWebSocket(), 3000);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    async controlBot(action) {
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');
        
        // Disable buttons during action
        startBtn.disabled = true;
        stopBtn.disabled = true;
        
        try {
            const response = await fetch('/api/control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ action })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showSuccess(result.message);
            } else {
                this.showError(result.error || 'Failed to control bot');
            }
        } catch (error) {
            console.error('Failed to control bot:', error);
            this.showError('Failed to communicate with server');
        } finally {
            // Re-enable buttons
            startBtn.disabled = false;
            stopBtn.disabled = false;
        }
    }

    updateUI(data) {
        if (data.error) {
            this.showError(data.error);
            return;
        }

        // Ensure DOM is ready before updating
        if (document.readyState === 'loading') {
            console.log('DOM not ready, waiting...');
            setTimeout(() => this.updateUI(data), 100);
            return;
        }

        try {
            // Update bot status
            this.updateBotStatus(data.bot);
        } catch (error) {
            console.error('Error updating bot status:', error);
        }
        
        try {
            // Update wallets
            this.updateWallets(data.wallets);
        } catch (error) {
            console.error('Error updating wallets:', error);
        }
        
        try {
            // Update markets
            this.updateMarkets(data.markets);
        } catch (error) {
            console.error('Error updating markets:', error);
        }
        
        try {
            // Update activity feed
            this.updateActivityFeed(data.logs);
        } catch (error) {
            console.error('Error updating activity feed:', error);
        }
    }

    updateBotStatus(bot, retryCount = 0) {
        const statusIndicator = document.getElementById('status-indicator');
        const botStatus = document.getElementById('bot-status');
        const botUptime = document.getElementById('bot-uptime');
        const botStarted = document.getElementById('bot-started');
        const botNetwork = document.getElementById('bot-network');
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');

        // Check if all required elements exist
        if (!statusIndicator || !botStatus || !botUptime || !botStarted || !botNetwork || !startBtn || !stopBtn) {
            console.error('Missing DOM elements for bot status update:', {
                statusIndicator: !!statusIndicator,
                botStatus: !!botStatus,
                botUptime: !!botUptime,
                botStarted: !!botStarted,
                botNetwork: !!botNetwork,
                startBtn: !!startBtn,
                stopBtn: !!stopBtn
            });
            
            // Retry after a short delay (max 3 retries)
            if (retryCount < 3) {
                setTimeout(() => {
                    console.log(`Retrying bot status update... (attempt ${retryCount + 1})`);
                    this.updateBotStatus(bot, retryCount + 1);
                }, 500);
            } else {
                console.error('Max retries reached for bot status update');
            }
            return;
        }

        const wasRunning = this.botRunning;
        this.botRunning = bot.running;
        
        // Update WebSocket status if bot status changed
        if (wasRunning !== this.botRunning) {
            this.updateWebSocketStatus(this.isConnected);
        }

        if (bot.running) {
            statusIndicator.innerHTML = '<span class="status-indicator status-running"></span><span id="status-text" class="text-sm font-medium">RUNNING</span>';
            botStatus.textContent = 'Running';
            botUptime.textContent = bot.uptime || '--:--:--';
            botStarted.textContent = bot.started_at ? new Date(bot.started_at).toLocaleTimeString() : 'Unknown';
            botNetwork.textContent = bot.network || 'Testnet';
            
            startBtn.disabled = true;
            stopBtn.disabled = false;
            
            // Start auto-refresh when bot starts running
            if (!wasRunning) {
                this.startBalanceAutoRefresh();
                this.updateRefreshButtonStatus();
            }
        } else {
            statusIndicator.innerHTML = '<span class="status-indicator status-stopped"></span><span id="status-text" class="text-sm font-medium">STOPPED</span>';
            botStatus.textContent = 'Stopped';
            botUptime.textContent = '--:--:--';
            botStarted.textContent = 'Never';
            botNetwork.textContent = bot.network || 'Testnet';
            
            startBtn.disabled = false;
            stopBtn.disabled = true;
            
            // Stop auto-refresh when bot stops
            if (wasRunning) {
                this.stopBalanceAutoRefresh();
                this.updateRefreshButtonStatus();
            }
        }
    }

    updateWallets(wallets) {
        document.getElementById('wallets-enabled').textContent = wallets.enabled;
        document.getElementById('wallets-total').textContent = wallets.total;
        
        const walletList = document.getElementById('wallet-list');
        if (wallets.list && wallets.list.length > 0) {
            walletList.innerHTML = wallets.list.map(w => 
                `<div class="text-success">• ${w.name} (${w.id})</div>`
            ).join('');
        } else {
            walletList.innerHTML = '<div class="text-gray-500">No wallets configured</div>';
        }
    }

    updateMarkets(markets) {
        document.getElementById('markets-enabled').textContent = markets.enabled;
        
        const marketList = document.getElementById('market-list');
        if (markets.list && markets.list.length > 0) {
            marketList.innerHTML = markets.list.map(m => 
                `<div class="text-success">• ${m.symbol} (${m.type})</div>`
            ).join('');
        } else {
            marketList.innerHTML = '<div class="text-gray-500">No markets configured</div>';
        }
    }

    updateActivityFeed(logs) {
        console.log('Updating activity feed with', logs?.length || 0, 'logs');
        const activityFeed = document.getElementById('activity-feed');
        
        if (!logs || logs.length === 0) {
            activityFeed.innerHTML = '<div class="text-center text-gray-500 py-8">No activity yet</div>';
            return;
        }

        // Check if logs have actually changed to avoid unnecessary updates
        const currentLogs = JSON.stringify(logs);
        if (this.lastLogs === currentLogs) {
            console.log('📝 Activity feed: No new logs, skipping update');
            return;
        }
        this.lastLogs = currentLogs;

        // Add a subtle animation to show the feed is updating
        activityFeed.style.opacity = '0.7';
        setTimeout(() => {
            activityFeed.style.opacity = '1';
        }, 100);

        // Log activity feed updates
        console.log(`📝 Activity feed updated with ${logs.length} logs at ${new Date().toLocaleTimeString()}`);

        const htmlContent = logs.map(log => {
            const timestamp = log.timestamp || 'Unknown';
            const message = log.message || '';
            
            // Determine log type and styling
            let logClass = 'text-gray-300';
            let icon = '📝';
            
            if (message.includes('✅')) {
                logClass = 'text-success';
                icon = '✅';
            } else if (message.includes('❌')) {
                logClass = 'text-danger';
                icon = '❌';
            } else if (message.includes('⚠️')) {
                logClass = 'text-warning';
                icon = '⚠️';
            } else if (message.includes('🚀')) {
                logClass = 'text-blue-400';
                icon = '🚀';
            } else if (message.includes('💰')) {
                logClass = 'text-yellow-400';
                icon = '💰';
            }
            
            return `
                <div class="log-entry fade-in flex items-start space-x-3 py-2 border-b border-gray-700 last:border-b-0">
                    <span class="text-gray-500 text-xs mt-1 min-w-[80px]">${timestamp}</span>
                    <span class="text-lg">${icon}</span>
                    <span class="${logClass} flex-1">${message}</span>
                </div>
            `;
        }).join('');
        
        activityFeed.innerHTML = htmlContent;
        
        // Auto-scroll to bottom
        activityFeed.scrollTop = activityFeed.scrollHeight;
    }

    toggleBalanceDetails() {
        const detailsSection = document.getElementById('balance-details');
        const toggleText = document.getElementById('toggle-text');
        
        if (detailsSection.classList.contains('hidden')) {
            detailsSection.classList.remove('hidden');
            toggleText.textContent = 'Hide Details';
        } else {
            detailsSection.classList.add('hidden');
            toggleText.textContent = 'Show Details';
        }
    }

    updateBalances(data) {
        const balanceSummary = document.getElementById('balance-summary');
        const balanceContainer = document.getElementById('balance-container');
        
        if (data.error) {
            balanceSummary.innerHTML = `
                <div class="col-span-full text-center text-red-400 py-4">
                    <div class="text-xl mb-2">❌</div>
                    <div class="font-medium">Error loading balances</div>
                    <div class="text-sm text-gray-500 mt-1">${data.error}</div>
                </div>
            `;
            return;
        }

        if (!data.wallets || Object.keys(data.wallets).length === 0) {
            balanceSummary.innerHTML = `
                <div class="col-span-full text-center text-gray-500 py-4">
                    <div class="text-xl mb-2">💰</div>
                    <div class="font-medium">No wallet balances available</div>
                </div>
            `;
            return;
        }

        // Create compact summary cards
        const summaryHTML = Object.entries(data.wallets).map(([walletId, walletData]) => {
            if (walletData.error) {
                return `
                    <div class="bg-gray-800 rounded-lg p-3 border border-gray-600">
                        <div class="flex items-center justify-between mb-2">
                            <h4 class="font-medium text-white text-sm">${walletData.name || walletId}</h4>
                            <span class="text-xs text-red-400">Error</span>
                        </div>
                        <div class="text-red-400 text-xs">${walletData.error}</div>
                    </div>
                `;
            }

            const tokens = walletData.tokens || [];
            const injToken = tokens.find(t => t.symbol === 'INJ');
            const stinjToken = tokens.find(t => t.symbol === 'stINJ');
            const usdtToken = tokens.find(t => t.symbol === 'USDT');
            
            return `
                <div class="bg-gray-800 rounded-lg p-3 border border-gray-600">
                    <div class="flex items-center justify-between mb-2">
                        <h4 class="font-medium text-white text-sm">${walletData.name || walletId}</h4>
                        <span class="text-xs text-gray-400">${tokens.length} tokens</span>
                    </div>
                    <div class="space-y-1">
                        ${injToken ? `<div class="flex justify-between text-xs"><span class="text-gray-400">INJ:</span><span class="text-white">${parseFloat(injToken.balance).toFixed(2)}</span></div>` : ''}
                        ${stinjToken ? `<div class="flex justify-between text-xs"><span class="text-gray-400">stINJ:</span><span class="text-white">${parseFloat(stinjToken.balance).toFixed(2)}</span></div>` : ''}
                        ${usdtToken ? `<div class="flex justify-between text-xs"><span class="text-gray-400">USDT:</span><span class="text-white">${parseFloat(usdtToken.balance).toFixed(2)}</span></div>` : ''}
                        ${tokens.length > 3 ? `<div class="text-xs text-gray-500 text-center pt-1">+${tokens.length - 3} more tokens</div>` : ''}
                    </div>
                </div>
            `;
        }).join('');

        balanceSummary.innerHTML = summaryHTML;

        // Create detailed view (same as before)
        const detailedHTML = Object.entries(data.wallets).map(([walletId, walletData]) => {
            if (walletData.error) {
                return `
                    <div class="bg-gray-800 rounded-lg p-4 border border-gray-600">
                        <div class="flex items-center justify-between mb-3">
                            <h4 class="font-semibold text-white">${walletData.name || walletId}</h4>
                            <span class="text-xs text-red-400">Error</span>
                        </div>
                        <div class="text-red-400 text-sm">${walletData.error}</div>
                    </div>
                `;
            }

            const tokens = walletData.tokens || [];
            const totalTokens = walletData.total_tokens || 0;
            const lastUpdated = walletData.last_updated ? new Date(walletData.last_updated).toLocaleTimeString() : 'Unknown';

            return `
                <div class="bg-gray-800 rounded-lg p-4 border border-gray-600">
                    <div class="flex items-center justify-between mb-3">
                        <h4 class="font-semibold text-white">${walletData.name || walletId}</h4>
                        <div class="text-right">
                            <div class="text-xs text-gray-400">${totalTokens} tokens</div>
                            <div class="text-xs text-gray-500">Updated: ${lastUpdated}</div>
                        </div>
                    </div>
                    
                    <div class="space-y-2">
                        ${tokens.length > 0 ? tokens.map(token => `
                            <div class="flex items-center justify-between py-2 px-3 bg-gray-700 rounded">
                                <div class="flex items-center space-x-3">
                                    <div class="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-xs font-bold">
                                        ${token.symbol ? token.symbol.charAt(0) : '?'}
                                    </div>
                                    <div>
                                        <div class="font-medium text-white">${token.symbol || 'Unknown'}</div>
                                        <div class="text-xs text-gray-400">${token.name || 'Unknown Token'}</div>
                                    </div>
                                </div>
                                <div class="text-right">
                                    <div class="font-medium text-white">${token.balance || '0'}</div>
                                    ${token.usd_value ? `<div class="text-xs text-green-400">$${parseFloat(token.usd_value).toFixed(2)}</div>` : ''}
                                </div>
                            </div>
                        `).join('') : `
                            <div class="text-center text-gray-500 py-4">
                                <div class="text-sm">No tokens found</div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        }).join('');

        balanceContainer.innerHTML = detailedHTML;
        
        // Update refresh button status
        this.updateRefreshButtonStatus();
        
        // Update WebSocket status indicator
        this.updateWebSocketStatus(this.isConnected);
    }

    updateRefreshButtonStatus() {
        const refreshText = document.getElementById('refresh-text');
        if (this.botRunning) {
            refreshText.textContent = 'Refresh (Auto)';
        } else {
            refreshText.textContent = 'Refresh';
        }
    }

    updateWebSocketStatus(connected) {
        const wsStatus = document.getElementById('websocket-status');
        if (wsStatus) {
            const indicator = wsStatus.querySelector('span:first-child');
            const text = wsStatus.querySelector('span:last-child');
            
            if (connected) {
                if (this.botRunning) {
                    indicator.className = 'w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse';
                    text.textContent = 'Live Updates (2s)';
                } else {
                    indicator.className = 'w-2 h-2 bg-yellow-500 rounded-full mr-2';
                    text.textContent = 'Connected (10s)';
                }
            } else {
                indicator.className = 'w-2 h-2 bg-red-500 rounded-full mr-2';
                text.textContent = 'Disconnected';
            }
        }
    }

    async refreshLogs() {
        console.log('Manually refreshing logs...');
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            this.updateActivityFeed(data.logs);
        } catch (error) {
            console.error('Failed to refresh logs:', error);
        }
    }

    async viewFullLogs() {
        console.log('Opening full logs modal...');
        try {
            // Show the modal
            const modal = document.getElementById('log-modal');
            modal.classList.remove('hidden');
            
            // Load the full logs
            await this.refreshFullLogs();
        } catch (error) {
            console.error('Failed to open full logs:', error);
            this.showError('Failed to open full logs');
        }
    }

    closeLogModal() {
        const modal = document.getElementById('log-modal');
        modal.classList.add('hidden');
    }

    async refreshFullLogs() {
        try {
            const response = await fetch('/api/logs/full');
            const content = await response.text();
            
            const logContent = document.getElementById('log-content');
            const logInfo = document.getElementById('log-info');
            
            logContent.textContent = content;
            
            // Update info
            const lines = content.split('\n').length;
            const size = new Blob([content]).size;
            logInfo.textContent = `${lines} lines • ${(size / 1024).toFixed(1)} KB • Last updated: ${new Date().toLocaleTimeString()}`;
            
        } catch (error) {
            console.error('Failed to refresh full logs:', error);
            document.getElementById('log-content').textContent = 'Error loading logs: ' + error.message;
        }
    }

    // Open Orders Methods
    async refreshOrders() {
        const refreshText = document.getElementById('orders-refresh-text');
        refreshText.textContent = 'Refreshing...';
        
        try {
            const response = await fetch('/api/open-orders');
            const data = await response.json();
            this.updateOrders(data);
        } catch (error) {
            console.error('Failed to refresh orders:', error);
            this.showError('Failed to refresh orders');
        } finally {
            refreshText.textContent = 'Refresh';
        }
    }

    updateOrders(data) {
        const ordersContainer = document.getElementById('orders-container');
        const ordersTotalBadge = document.getElementById('orders-total-badge');
        
        if (data.error) {
            ordersContainer.innerHTML = `
                <div class="text-center text-red-400 py-4">
                    <div class="text-xl mb-2">❌</div>
                    <div class="font-medium">Error loading orders</div>
                    <div class="text-sm text-gray-500 mt-1">${data.error}</div>
                </div>
            `;
            ordersTotalBadge.textContent = '0';
            return;
        }

        const totalOrders = data.total_orders || 0;
        ordersTotalBadge.textContent = totalOrders;

        if (totalOrders === 0) {
            ordersContainer.innerHTML = `
                <div class="text-center text-gray-500 py-8">
                    <div class="text-2xl mb-2">📊</div>
                    <div class="font-medium">No open orders</div>
                    <div class="text-sm text-gray-400 mt-1">All wallets are clean</div>
                </div>
            `;
            return;
        }

        // Group orders by wallet
        const walletSummaries = [];
        Object.entries(data.wallets || {}).forEach(([walletId, walletData]) => {
            if (walletData.total_orders > 0) {
                const marketSummaries = [];
                let walletTotalOrders = 0;
                let walletTotalValue = 0;

                Object.entries(walletData.markets || {}).forEach(([marketId, marketData]) => {
                    const spotOrders = marketData.spot_orders || [];
                    const derivativeOrders = marketData.derivative_orders || [];
                    const allMarketOrders = [...spotOrders, ...derivativeOrders];
                    
                    if (allMarketOrders.length > 0) {
                        // Calculate market statistics
                        const marketTotalOrders = allMarketOrders.length;
                        const marketTotalQuantity = allMarketOrders.reduce((sum, order) => sum + parseFloat(order.quantity || 0), 0);
                        const marketAvgPrice = allMarketOrders.reduce((sum, order) => sum + parseFloat(order.price || 0), 0) / marketTotalOrders;
                        const marketTotalValue = marketTotalQuantity * marketAvgPrice;
                        
                        // Count by order type
                        const spotCount = spotOrders.length;
                        const derivativeCount = derivativeOrders.length;
                        
                        // Count by side
                        const buyOrders = allMarketOrders.filter(order => order.orderSide === 'buy').length;
                        const sellOrders = allMarketOrders.filter(order => order.orderSide === 'sell').length;
                        
                        // Count by state
                        const openOrders = allMarketOrders.filter(order => order.state === 'booked').length;
                        const partialOrders = allMarketOrders.filter(order => order.state === 'partial_filled').length;
                        const activeOrders = allMarketOrders.filter(order => order.state === 'active').length;

                        marketSummaries.push({
                            marketId,
                            totalOrders: marketTotalOrders,
                            spotCount,
                            derivativeCount,
                            buyOrders,
                            sellOrders,
                            openOrders,
                            partialOrders,
                            activeOrders,
                            avgPrice: marketAvgPrice,
                            totalQuantity: marketTotalQuantity,
                            totalValue: marketTotalValue,
                            orders: allMarketOrders
                        });

                        walletTotalOrders += marketTotalOrders;
                        walletTotalValue += marketTotalValue;
                    }
                });

                if (marketSummaries.length > 0) {
                    walletSummaries.push({
                        walletId,
                        walletName: walletData.name || walletId,
                        totalOrders: walletTotalOrders,
                        totalValue: walletTotalValue,
                        markets: marketSummaries
                    });
                }
            }
        });

        // Sort wallets by total orders (descending)
        walletSummaries.sort((a, b) => b.totalOrders - a.totalOrders);

        const walletCardsHTML = walletSummaries.map(wallet => `
            <div class="bg-gray-800/50 rounded-lg border border-gray-700 mb-4">
                <div class="p-4 border-b border-gray-700">
                    <div class="flex items-center justify-between">
                        <h4 class="text-lg font-semibold text-white">${wallet.walletName}</h4>
                        <div class="flex items-center space-x-4">
                            <span class="text-sm text-gray-400">Total Orders:</span>
                            <span class="bg-blue-600 text-white px-3 py-1 rounded-full text-sm font-medium">${wallet.totalOrders}</span>
                        </div>
                    </div>
                </div>
                <div class="p-4">
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        ${wallet.markets.map(market => `
                            <div class="bg-gray-900/50 rounded-lg p-4 border border-gray-600">
                                <div class="flex items-center justify-between mb-3">
                                    <h5 class="font-medium text-blue-400">${market.marketId}</h5>
                                    <span class="bg-orange-600 text-white px-2 py-1 rounded text-xs">${market.totalOrders} orders</span>
                                </div>
                                
                                <div class="space-y-2 text-sm">
                                    <div class="flex justify-between">
                                        <span class="text-gray-400">Type:</span>
                                        <div class="flex space-x-1">
                                            ${market.spotCount > 0 ? `<span class="bg-green-900 text-green-300 px-2 py-1 rounded text-xs">${market.spotCount} SPOT</span>` : ''}
                                            ${market.derivativeCount > 0 ? `<span class="bg-purple-900 text-purple-300 px-2 py-1 rounded text-xs">${market.derivativeCount} DERIV</span>` : ''}
                                        </div>
                                    </div>
                                    
                                    <div class="flex justify-between">
                                        <span class="text-gray-400">Side:</span>
                                        <div class="flex space-x-1">
                                            ${market.buyOrders > 0 ? `<span class="bg-green-600 text-white px-2 py-1 rounded text-xs">${market.buyOrders} BUY</span>` : ''}
                                            ${market.sellOrders > 0 ? `<span class="bg-red-600 text-white px-2 py-1 rounded text-xs">${market.sellOrders} SELL</span>` : ''}
                                        </div>
                                    </div>
                                    
                                    <div class="flex justify-between">
                                        <span class="text-gray-400">State:</span>
                                        <div class="flex space-x-1">
                                            ${market.openOrders > 0 ? `<span class="bg-blue-600 text-white px-2 py-1 rounded text-xs">${market.openOrders} open</span>` : ''}
                                            ${market.partialOrders > 0 ? `<span class="bg-orange-600 text-white px-2 py-1 rounded text-xs">${market.partialOrders} partial</span>` : ''}
                                            ${market.activeOrders > 0 ? `<span class="bg-green-600 text-white px-2 py-1 rounded text-xs">${market.activeOrders} active</span>` : ''}
                                        </div>
                                    </div>
                                    
                                    <div class="flex justify-between">
                                        <span class="text-gray-400">Avg Price:</span>
                                        <span class="text-yellow-400 font-mono">${this.formatPrice(market.avgPrice)}</span>
                                    </div>
                                    
                                    <div class="flex justify-between">
                                        <span class="text-gray-400">Total Qty:</span>
                                        <span class="text-cyan-400 font-mono">${this.formatQuantity(market.totalQuantity)}</span>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `).join('');

        ordersContainer.innerHTML = `
            <div class="space-y-4">
                ${walletCardsHTML}
            </div>
            <div class="mt-4 text-xs text-gray-500 text-center">
                Showing ${totalOrders} orders across ${walletSummaries.length} wallets
            </div>
        `;
    }

    formatPrice(price) {
        if (!price) return 'N/A';
        const num = parseFloat(price);
        
        // For very small prices (likely in smallest unit), convert to readable format
        if (num < 0.000001) {
            // Convert to a more readable format by multiplying by 1e12
            const readablePrice = num * 1e12;
            return readablePrice.toFixed(3);
        } else if (num < 0.01) {
            return num.toFixed(8);
        } else if (num < 1) {
            return num.toFixed(6);
        } else {
            return num.toFixed(4);
        }
    }

    formatQuantity(quantity) {
        if (!quantity) return 'N/A';
        const num = parseFloat(quantity);
        
        // For very large quantities (likely in smallest unit), convert to readable format
        if (num >= 1e18) {
            // Convert from wei/smallest unit to tokens (divide by 1e18)
            const readableQuantity = num / 1e18;
            if (readableQuantity >= 1000000) {
                return (readableQuantity / 1000000).toFixed(1) + 'M';
            } else if (readableQuantity >= 1000) {
                return (readableQuantity / 1000).toFixed(1) + 'K';
            } else {
                return readableQuantity.toFixed(0);
            }
        } else if (num >= 1000000000000) {
            return (num / 1000000000000).toFixed(1) + 'T';
        } else if (num >= 1000000000) {
            return (num / 1000000000).toFixed(1) + 'B';
        } else if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        } else {
            return num.toFixed(0);
        }
    }

    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showError(message) {
        this.showNotification(message, 'error');
    }

    showNotification(message, type) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg max-w-sm fade-in ${
            type === 'success' ? 'bg-success text-white' : 'bg-danger text-white'
        }`;
        notification.innerHTML = `
            <div class="flex items-center">
                <span class="mr-2">${type === 'success' ? '✅' : '❌'}</span>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    new TradingBotDashboard();
});
