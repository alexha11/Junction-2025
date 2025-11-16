#!/bin/bash
# Test WebSocket connection and show all messages

WEBSOCKET_URL="ws://localhost:8000/system/demo/simulate?speed_multiplier=10.0"

echo "========================================"
echo "WebSocket Test Script"
echo "========================================"
echo "Connecting to: $WEBSOCKET_URL"
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# Use websocat if available, otherwise use wscat or curl
if command -v websocat &> /dev/null; then
    echo "Using websocat..."
    websocat "$WEBSOCKET_URL"
elif command -v wscat &> /dev/null; then
    echo "Using wscat..."
    wscat -c "$WEBSOCKET_URL"
elif command -v curl &> /dev/null; then
    echo "Using curl (limited WebSocket support)..."
    echo "Note: curl doesn't fully support WebSocket. Install websocat or wscat for better testing."
    curl -i -N \
        -H "Connection: Upgrade" \
        -H "Upgrade: websocket" \
        -H "Sec-WebSocket-Version: 13" \
        -H "Sec-WebSocket-Key: $(echo -n "test" | base64)" \
        "$WEBSOCKET_URL"
else
    echo "ERROR: No WebSocket client found!"
    echo "Install one of:"
    echo "  - websocat: cargo install websocat"
    echo "  - wscat: npm install -g wscat"
    exit 1
fi

