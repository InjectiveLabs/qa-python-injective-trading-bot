/**
 * Simple Trading Bot Manager - Frontend JavaScript
 * Handles bot management, wallet selection, and process monitoring
 */

class BotManager {
    constructor() {
        this.availableWallets = [];
        this.runningBots = [];
        this.markets = {
            spot: [],
            derivative: []
        };
        this.currentBotForLogs = null; // Track which bot's logs we're viewing
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadInitialData();
        // Refresh status every 10 seconds
        setInterval(() => this.refreshStatus(), 10000);
        // Refresh logs every 5 seconds
        setInterval(() => this.refreshLogs(), 5000);
    }

    setupEventListeners() {
        // Bot type selection
        document.querySelectorAll('input[name="bot-type"]').forEach(radio => {
            radio.addEventListener('change', () => this.onBotTypeChange());
        });

        // Form submission
        document.getElementById('bot-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.startBot();
        });

        // Wallet and market selection to enable/disable start button
        document.addEventListener('change', (e) => {
            if (e.target.id === 'wallet-select' || e.target.name === 'market') {
                this.updateStartButtonState();
            }
        });
    }

    async loadInitialData() {
        try {
            await Promise.all([
                this.loadWallets(),
                this.loadMarkets(),
                this.refreshStatus()
            ]);
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.showMessage('Failed to load initial data', 'error');
        }
    }

    async loadWallets() {
        try {
            const response = await fetch('/api/wallets');
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.availableWallets = data.wallets || [];
            this.updateWalletSelection();
        } catch (error) {
            console.error('Failed to load wallets:', error);
            this.showMessage('Failed to load wallets', 'error');
        }
    }

    async loadMarkets() {
        try {
            const response = await fetch('/api/markets');
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.markets = data.markets || { spot: [], derivative: [] };
        } catch (error) {
            console.error('Failed to load markets:', error);
            this.showMessage('Failed to load markets', 'error');
        }
    }

    updateWalletSelection() {
        const select = document.getElementById('wallet-select');
        
        if (this.availableWallets.length === 0) {
            select.innerHTML = '<option value="">No wallets configured</option>';
            select.disabled = true;
            return;
        }

        // Get list of wallets currently in use
        const walletsInUse = this.runningBots.map(bot => bot.wallet_id);

        // Separate available and in-use wallets
        const availableWallets = [];
        const inUseWallets = [];

        this.availableWallets.forEach(wallet => {
            if (walletsInUse.includes(wallet.id)) {
                inUseWallets.push(wallet);
            } else {
                availableWallets.push(wallet);
            }
        });

        // Build dropdown options
        let optionsHtml = '<option value="">-- Select a wallet --</option>';
        
        // Add available wallets first
        if (availableWallets.length > 0) {
            optionsHtml += '<optgroup label="Available Wallets">';
            availableWallets.forEach(wallet => {
                optionsHtml += `<option value="${wallet.id}">✓ ${wallet.name}</option>`;
            });
            optionsHtml += '</optgroup>';
        }
        
        // Add in-use wallets at the bottom (disabled)
        if (inUseWallets.length > 0) {
            optionsHtml += '<optgroup label="In Use">';
            inUseWallets.forEach(wallet => {
                optionsHtml += `<option value="${wallet.id}" disabled>⊗ ${wallet.name} (In Use)</option>`;
            });
            optionsHtml += '</optgroup>';
        }

        select.innerHTML = optionsHtml;
        select.disabled = false;
    }

    onBotTypeChange() {
        const selectedType = document.querySelector('input[name="bot-type"]:checked')?.value;
        if (!selectedType) return;

        this.updateMarketSelection(selectedType);
        this.updateStartButtonState();
    }

    updateMarketSelection(botType) {
        const container = document.getElementById('market-selection');
        const availableMarkets = this.markets[botType] || [];

        if (availableMarkets.length === 0) {
            container.innerHTML = `<p class="error">No ${botType} markets configured</p>`;
            return;
        }

        container.innerHTML = availableMarkets.map(market => `
            <div class="radio-item">
                <input type="radio" id="market-${market.symbol}" name="market" value="${market.symbol}">
                <label for="market-${market.symbol}">${market.symbol}</label>
            </div>
        `).join('');
    }

    updateStartButtonState() {
        const botType = document.querySelector('input[name="bot-type"]:checked');
        const wallet = document.getElementById('wallet-select').value;
        const market = document.querySelector('input[name="market"]:checked');
        
        const startBtn = document.getElementById('start-bot-btn');
        startBtn.disabled = !(botType && wallet && market);
    }

    async startBot() {
        const formData = new FormData(document.getElementById('bot-form'));
        const botType = formData.get('bot-type');
        const walletId = document.getElementById('wallet-select').value;
        const market = formData.get('market');

        if (!botType || !walletId || !market) {
            this.showMessage('Please select bot type, wallet, and market', 'error');
            return;
        }

        try {
            this.showMessage('Starting bot...', 'info');
            
            const response = await fetch('/api/start-bot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bot_type: botType,
                    wallet_id: walletId,
                    market: market
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showMessage(result.message || 'Bot started successfully', 'success');
                // Clear form selections
                document.getElementById('bot-form').reset();
                this.updateStartButtonState();
                // Refresh status immediately
                setTimeout(() => this.refreshStatus(), 2000);
            } else {
                this.showMessage(result.error || 'Failed to start bot', 'error');
            }
        } catch (error) {
            console.error('Failed to start bot:', error);
            this.showMessage('Failed to communicate with server', 'error');
        }
    }

    async stopBot(walletId, containerId) {
        if (!confirm(`Stop bot for ${walletId}?`)) {
            return;
        }

        try {
            const response = await fetch('/api/stop-bot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wallet_id: walletId,
                    container_id: containerId
                })
            });

            const result = await response.json();
            
            if (result.success) {
                this.showMessage(result.message || 'Bot stopped successfully', 'success');
                // Refresh status immediately
                setTimeout(() => this.refreshStatus(), 1000);
            } else {
                this.showMessage(result.error || 'Failed to stop bot', 'error');
            }
        } catch (error) {
            console.error('Failed to stop bot:', error);
            this.showMessage('Failed to communicate with server', 'error');
        }
    }

    async refreshStatus() {
        try {
            const response = await fetch('/api/running-bots');
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.runningBots = data.bots || [];
            this.updateRunningBotsDisplay();
            this.updateWalletSelection(); // Update wallet availability
        } catch (error) {
            console.error('Failed to refresh status:', error);
        }
    }

    updateRunningBotsDisplay() {
        const container = document.getElementById('running-bots');
        
        if (this.runningBots.length === 0) {
            container.innerHTML = '<p>No bots currently running</p>';
            return;
        }

        container.innerHTML = this.runningBots.map(bot => {
            // Format wallet balance display
            let balanceHtml = '';
            if (bot.wallet_balance && bot.wallet_balance.balances) {
                const balances = bot.wallet_balance.balances;
                const balanceItems = Object.entries(balances).map(([symbol, data]) => 
                    `${symbol}: ${parseFloat(data.balance).toFixed(2)}`
                ).join(' | ');
                balanceHtml = `
                    <div class="bot-info-section">
                        <strong>💰 Wallet Balance:</strong> ${balanceItems}
                    </div>
                `;
            } else if (bot.wallet_balance && bot.wallet_balance.error) {
                balanceHtml = `
                    <div class="bot-info-section error">
                        <strong>💰 Wallet Balance:</strong> ${bot.wallet_balance.error}
                    </div>
                `;
            }

            // Format market prices display
            let pricesHtml = '';
            if (bot.market_prices) {
                const prices = bot.market_prices;
                if (prices.error) {
                    pricesHtml = `
                        <div class="bot-info-section error">
                            <strong>📈 Market Prices:</strong> ${prices.error}
                        </div>
                    `;
                } else {
                    const testnetPrice = prices.testnet_price ? `$${parseFloat(prices.testnet_price).toFixed(4)}` : 'N/A';
                    const mainnetPrice = prices.mainnet_price ? `$${parseFloat(prices.mainnet_price).toFixed(4)}` : 'N/A';
                    let differenceHtml = '';
                    
                    if (prices.price_difference !== null && prices.price_difference !== undefined) {
                        const diff = parseFloat(prices.price_difference);
                        const diffColor = diff > 0 ? 'color: #dc3545' : diff < 0 ? 'color: #28a745' : 'color: #666';
                        const diffSign = diff > 0 ? '+' : '';
                        differenceHtml = `<span style="${diffColor}"> (${diffSign}${diff.toFixed(2)}%)</span>`;
                    }
                    
                    pricesHtml = `
                        <div class="bot-info-section">
                            <strong>📈 Prices:</strong> 
                            Testnet: ${testnetPrice} | 
                            Mainnet: ${mainnetPrice}${differenceHtml}
                        </div>
                    `;
                }
            }

            return `
                <div class="running-bot">
                    <div class="running-bot-header">
                        ${bot.wallet_id}: ${bot.bot_type} Trader (${bot.market})
                    </div>
                    <div class="running-bot-info">
                        Container: ${bot.container_id} | Started: ${new Date(bot.started_at).toLocaleString()} | Uptime: ${bot.uptime}
                    </div>
                    ${balanceHtml}
                    ${pricesHtml}
                    <div class="bot-controls">
                        <button class="danger" onclick="botManager.stopBot('${bot.wallet_id}', '${bot.container_id}')">
                            Stop Bot
                        </button>
                        <button onclick="botManager.viewBotLogs('${bot.wallet_id}', '${bot.bot_type}')">
                            View Logs
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    async refreshLogs() {
        try {
            const response = await fetch('/api/recent-logs');
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.updateLogsDisplay(data.logs || []);
        } catch (error) {
            console.error('Failed to refresh logs:', error);
        }
    }

    updateLogsDisplay(logs) {
        const container = document.getElementById('log-container');
        
        if (logs.length === 0) {
            container.innerHTML = 'No recent logs';
            return;
        }

        const logHtml = logs.map(log => 
            `[${log.timestamp}] ${log.message}`
        ).join('\n');
        
        container.textContent = logHtml;
        // Auto-scroll to bottom
        container.scrollTop = container.scrollHeight;
    }

    async viewBotLogs(walletId, botType) {
        this.currentBotForLogs = { walletId, botType };
        
        // Update modal title
        document.getElementById('modal-bot-title').textContent = 
            `${walletId} - ${botType.charAt(0).toUpperCase() + botType.slice(1)} Trader Logs`;
        
        // Show modal
        const modal = document.getElementById('bot-log-modal');
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
        
        // Load logs for this specific bot
        await this.refreshBotLogs();
    }

    async refreshBotLogs() {
        if (!this.currentBotForLogs) return;
        
        try {
            const response = await fetch(`/api/bot-logs/${this.currentBotForLogs.walletId}/${this.currentBotForLogs.botType}`);
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.updateBotLogsDisplay(data.logs || []);
        } catch (error) {
            console.error('Failed to refresh bot logs:', error);
            document.getElementById('modal-log-container').textContent = 
                `Error loading logs: ${error.message}`;
        }
    }

    updateBotLogsDisplay(logs) {
        const container = document.getElementById('modal-log-container');
        
        if (logs.length === 0) {
            container.innerHTML = 'No logs found for this bot';
            return;
        }

        // Format: timestamp on its own line for readability
        const logHtml = logs.map(log => {
            const ts = log.timestamp || '';
            const msg = log.message || '';
            return `${ts}\n${msg}`;
        }).join('\n\n');
        
        container.textContent = logHtml;
        // Auto-scroll to bottom
        container.scrollTop = container.scrollHeight;
    }

    closeBotLogModal() {
        const modal = document.getElementById('bot-log-modal');
        modal.classList.add('hidden');
        modal.style.display = 'none';
        this.currentBotForLogs = null;
    }

    showMessage(message, type = 'info') {
        const messageDiv = document.getElementById('message');
        messageDiv.className = type;
        messageDiv.textContent = message;
        messageDiv.classList.remove('hidden');
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            messageDiv.classList.add('hidden');
        }, 5000);
    }
}

// Global functions for inline event handlers
function refreshStatus() {
    botManager.refreshStatus();
}

function refreshLogs() {
    botManager.refreshLogs();
}

function refreshBotLogs() {
    if (botManager.currentBotForLogs) {
        botManager.refreshBotLogs();
    }
}

function closeBotLogModal() {
    botManager.closeBotLogModal();
}

// Initialize when page loads
let botManager;
document.addEventListener('DOMContentLoaded', () => {
    botManager = new BotManager();
});