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
    }

    async loadInitialData() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            this.updateUI(data);
            
            // Load balance data
            await this.loadBalances();
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
