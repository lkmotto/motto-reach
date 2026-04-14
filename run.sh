#!/usr/bin/env bash
# run.sh — Cron wrapper for motto-outreach agent
# Called by cron every 2 hours and by sharpener cron daily.
# Handles env loading, locking (no overlapping runs), and error capture.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="/tmp/motto-outreach.lock"
LOG_DIR="$SCRIPT_DIR/logs"
ENV_FILE="$SCRIPT_DIR/.env"

mkdir -p "$LOG_DIR"

# ── Load .env ──────────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    set -o allexport
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +o allexport
fi

# ── Mode detection ────────────────────────────────────────────────
MODE="${1:-cycle}"  # cycle | sharpen | status | dry

case "$MODE" in
    cycle)   PYTHON_ARGS="--cycle" ;;
    sharpen) PYTHON_ARGS="" ; SCRIPT="sharpener.py" ;;
    status)  PYTHON_ARGS="--status" ;;
    dry)     PYTHON_ARGS="--cycle --dry-run" ;;
    *)       echo "Usage: run.sh [cycle|sharpen|status|dry]" ; exit 1 ;;
esac

# Default script is agent.py
SCRIPT="${SCRIPT:-agent.py}"

# ── Lock guard ────────────────────────────────────────────────────
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Another instance running (PID $PID). Exiting."
        exit 0
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stale lock found, removing."
        rm -f "$LOCK_FILE"
    fi
fi

echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ── Activate venv if present ──────────────────────────────────────
if [ -d "$SCRIPT_DIR/venv" ]; then
    # shellcheck disable=SC1090
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# ── Run ──────────────────────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting $SCRIPT $PYTHON_ARGS"

cd "$SCRIPT_DIR"
python3 "$SCRIPT" $PYTHON_ARGS 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done."
