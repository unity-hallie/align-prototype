#!/bin/bash
# ALIGN Prototype - Simple Start
# One command to run the app locally
# Usage: ./start.sh [PORT]
# Default port: 5000

set -e

echo "🚀 Starting ALIGN Prototype"
echo ""

# Configuration
PORT=${1:-5000}

# Stop any existing processes
echo "🧹 Cleaning up..."
pkill -f "python.*app.py" 2>/dev/null || true
sleep 1

# Create required directories
mkdir -p .local_context

# Start the app
echo "📦 Starting Flask app on http://127.0.0.1:$PORT"
echo ""

PORT=$PORT python3 app.py
