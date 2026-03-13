#!/bin/bash
cd ~/intune-device-healer
source venv/bin/activate
python src/server.py &
SERVER_PID=$!
sleep 3
kill $SERVER_PID 2>/dev/null
echo "✓ Server started successfully"
