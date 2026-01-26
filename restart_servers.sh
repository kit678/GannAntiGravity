#!/bin/bash

# Define the ports to kill
PORTS=("8001" "8005" "5173")

# Function to kill process by port
kill_port_process() {
    local port=$1
    local pid=$(netstat -ano 2>/dev/null | grep ":$port" | grep "LISTENING" | awk '{print $5}' | tr -d '\r' | head -1)
    
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
        echo "Killing process ID $pid on port $port..."
        taskkill //F //PID "$pid" //T > /dev/null 2>&1
    else
        echo "No process found on port $port."
    fi
}

# Kill processes on defined ports
for port in "${PORTS[@]}"; do
    kill_port_process "$port"
done

# Wait a moment to ensure ports are freed
sleep 2

# Define paths (Git Bash style)
BACKEND_PATH="/c/Dev/GannTesting/gann-visualizer/backend"
FRONTEND_PATH="/c/Dev/GannTesting/gann-visualizer/frontend"

# Start Backend Server (New Git Bash Window using MINGW64's start)
echo "Starting Backend Server..."
(cd "$BACKEND_PATH" && python main.py) &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Small delay before starting frontend
sleep 1

# Start Frontend Server
echo "Starting Frontend Server..."
(cd "$FRONTEND_PATH" && npm run dev) &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

echo ""
echo "========================================"
echo "Servers started in background!"
echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo ""
echo "To stop servers, run: kill $BACKEND_PID $FRONTEND_PID"
echo "Or close this terminal."
echo "========================================"

# Wait for both processes (keeps script running so servers stay alive)
wait
