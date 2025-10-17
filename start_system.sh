#!/bin/bash
# Start ALIGN Prototype System - Complete Cold Start
# Usage: ./start_system.sh

set -e

LOCK_FILE=".system.lock"
LOCK_TIMEOUT=30

# Check if already running
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(($(date +%s) - $(stat -f%m "$LOCK_FILE" 2>/dev/null || echo 0)))
    if [ $LOCK_AGE -lt $LOCK_TIMEOUT ]; then
        echo "❌ System is already starting/running!"
        echo ""
        echo "To stop it, run:"
        echo "   pkill -f 'traffic_router|app.py'"
        echo ""
        exit 1
    fi
fi

# Create lock file
mkdir -p .local_context
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

echo "🚀 Starting ALIGN Prototype System..."
echo ""

# Kill any existing processes
echo "🧹 Cleaning up old processes..."
pkill -f "traffic_router" 2>/dev/null || true
pkill -f "python3.*app.py" 2>/dev/null || true
sleep 1

# Create local context directory if needed
mkdir -p .local_context

# Remove stale state file for clean start
rm -f .local_context/bg_state.json

echo ""
echo "📦 Starting Blue Instance (port 5005)..."
python3 bin/blue_green_deploy start blue > /dev/null 2>&1

echo ""
echo "🌐 Starting Traffic Router (port 5004)..."
python3 utils/traffic_router.py start > .local_context/router.log 2>&1 &
sleep 2

echo ""
echo "✅ System Started Successfully!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📍 Access Points:"
echo "   • App:       http://localhost:5004"
echo "   • Analytics: http://localhost:5004/analytics"
echo ""
echo "🛑 Stop System:"
echo "   pkill -f 'traffic_router|app.py'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Quick health check
sleep 1
echo "🏥 Verifying system health..."
if curl -s http://localhost:5005/health > /dev/null 2>&1; then
    echo "   ✅ Blue instance healthy"
else
    echo "   ❌ Blue instance not responding"
    exit 1
fi

if curl -s http://localhost:5004/ > /dev/null 2>&1; then
    echo "   ✅ Router working"
else
    echo "   ❌ Router not responding"
    exit 1
fi

echo ""
echo "🎉 Ready to go! Open http://localhost:5004 in your browser"
echo ""
