#!/bin/bash

# SongClone dev runner - runs backend and frontend with combined logs

PIDS=()

cleanup() {
    echo ""
    echo "Shutting down..."

    # Kill tracked PIDs
    for pid in "${PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null
    done

    # Also kill anything on our ports
    lsof -ti :8000 | xargs kill -9 2>/dev/null
    lsof -ti :5173 | xargs kill -9 2>/dev/null

    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

cd "$(dirname "$0")"

# Start backend
echo "Starting backend on :8000..."
source venv/bin/activate
PYTHONUNBUFFERED=1 uvicorn songclone.api.main:app --reload --port 8000 2>&1 | sed 's/^/[API] /' &
PIDS+=($!)

# Start frontend
echo "Starting frontend..."
cd songclone/web
npm run dev 2>&1 | sed 's/^/[WEB] /' &
PIDS+=($!)

echo ""
echo "Press Ctrl+C to stop both"
echo ""

wait
