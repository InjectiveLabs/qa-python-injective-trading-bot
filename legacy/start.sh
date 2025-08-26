#!/bin/bash

# Injective Market Making Bot Startup Script

echo "🚀 Starting Injective Market Making Bot..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from template..."
    cp env.example .env
    echo "⚠️  Please edit .env file with your configuration before running the bot"
    exit 1
fi

# Run setup test
echo "🧪 Running setup test..."
python test_setup.py

# If test passes, start the bot
if [ $? -eq 0 ]; then
    echo "✅ Setup test passed! Starting bot..."
    python main.py
else
    echo "❌ Setup test failed! Please check your configuration."
    exit 1
fi
