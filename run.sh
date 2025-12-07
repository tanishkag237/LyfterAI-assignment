#!/bin/bash

# Exit on error
set -e

echo "Setting up Universal Website Scraper..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium

# Kill any existing process on port 8000
echo "Checking for existing server on port 8000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Start server
echo "Starting server on http://localhost:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000