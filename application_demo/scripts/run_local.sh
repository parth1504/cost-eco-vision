#!/bin/bash
# Run the demo application locally for testing
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../app"

echo "=== Starting Order Processing API (local mode) ==="

cd "$APP_DIR"

# Install deps if needed
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

export APP_ENV=development
export LOG_LEVEL=INFO
export INSTANCE_ID=i-local-dev
export LOG_CYCLE_MINUTES=5
export FAILURE_MODE=${1:-normal}

echo "Mode: $FAILURE_MODE"
echo "Log cycle: ${LOG_CYCLE_MINUTES}min"
echo "API: http://localhost:8080"
echo ""

python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
