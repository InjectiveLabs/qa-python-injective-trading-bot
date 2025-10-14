# Derivative Trader Dockerfile  
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies and build tools
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Clean up build tools (optional, saves ~100MB)
RUN apt-get purge -y gcc g++ make && apt-get autoremove -y

# Copy application code
COPY scripts/bots/derivative_trader.py ./derivative_trader.py
COPY config/ ./config/
COPY utils/ ./utils/
COPY data/ ./data/

# Create directories for logs
RUN mkdir -p /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the derivative trader
# Arguments will be passed by docker run command:
# - WALLET_ID (env var)
# - MARKETS (env var)
CMD python derivative_trader.py ${WALLET_ID} --markets ${MARKETS}

