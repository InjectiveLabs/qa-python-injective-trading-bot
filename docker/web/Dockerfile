# Web Dashboard Dockerfile
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

# Install Docker SDK for Python (for container management)
RUN pip install --no-cache-dir docker

# Copy application code
COPY web/ ./web/
COPY config/ ./config/
COPY utils/ ./utils/
COPY data/ ./data/
COPY *.py ./

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data

# Expose port 8000 for web dashboard
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the web application
CMD ["python", "web/app.py"]

