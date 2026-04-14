#!/usr/bin/env bash
# cron_setup.sh — Full install script for DigitalOcean droplet (138.197.2.28)
# Run as root: bash /opt/motto-outreach/cron_setup.sh
#
# What this does:
#   1. Installs system dependencies (Python, Playwright, Ollama)
#   2. Installs Python packages
#   3. Copies session files from motto-reddit/
#   4. Writes .env from secrets
#   5. Warms up Ollama (pulls llama3.1:8b, builds luke-motto)
#   6. Installs 2-hour cron + daily sharpener cron
#   7. Runs a dry-run to validate everything

set -euo pipefail

INSTALL_DIR="/opt/motto-outreach"
LOG_DIR="$INSTALL_DIR/logs"
DATA_DIR="$INSTALL_DIR/data"

echo "========================================"
echo " Motto Outreach — Droplet Setup"
echo " Target: $INSTALL_DIR"
echo "========================================"

# ── 1. System deps ────────────────────────────────────────────────
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl wget jq \
    chromium-browser \
    fonts-liberation libglib2.0-0 libnss3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2

# ── 2. Install Ollama ─────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    echo "[2/7] Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    # Start Ollama service
    systemctl enable ollama 2>/dev/null || true
    systemctl start ollama  2>/dev/null || ollama serve &>/dev/null &
    sleep 5
else
    echo "[2/7] Ollama already installed. Starting..."
    systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
    sleep 3
fi

# ── 3. Python venv + packages ─────────────────────────────────────
echo "[3/7] Setting up Python environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet \
    playwright \
    requests \
    python-dotenv

# Install Playwright browsers
python3 -m playwright install chromium --with-deps

# ── 4. Session files ──────────────────────────────────────────────
echo "[4/7] Setting up session files..."

# Reddit session — copy from motto-reddit if it exists
REDDIT_SESSION_SRC="/opt/motto-reddit/fast_session.json"
REDDIT_SESSION_DST="$DATA_DIR/fast_session.json"

if [ -f "$REDDIT_SESSION_SRC" ]; then
    cp "$REDDIT_SESSION_SRC" "$REDDIT_SESSION_DST"
    echo "  ✓ Reddit session copied from motto-reddit"
elif [ -f "$DATA_DIR/fast_session.json" ]; then
    echo "  ✓ Reddit session already in place"
else
    echo "  ⚠ No Reddit session found — you must upload fast_session.json to $DATA_DIR/"
    echo "    scp /home/user/workspace/motto-reddit/fast_session.json root@138.197.2.28:$DATA_DIR/"
fi

# X session placeholder
if [ ! -f "$DATA_DIR/x_session.json" ]; then
    echo '{}' > "$DATA_DIR/x_session.json"
    echo "  ⚠ No X session. Run: python3 x_client.py --login"
fi

# ── 5. Write .env from secrets ────────────────────────────────────
echo "[5/7] Writing .env..."

# If .env already exists, don't overwrite
if [ -f "$INSTALL_DIR/.env" ]; then
    echo "  .env already exists — skipping. Edit manually if needed."
else
    # Try to read GMAIL_APP_PASSWORD from environment (set before running this script)
    # e.g.: export GMAIL_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx" && bash cron_setup.sh
    GMAIL_APP_PASS="${GMAIL_APP_PASSWORD:-}"

    cat > "$INSTALL_DIR/.env" <<EOF
GMAIL_APP_PASSWORD=${GMAIL_APP_PASS}
REPORT_TO_EMAIL=ljm32901@gmail.com
REPORT_FROM_EMAIL=ljm32901@gmail.com
REDDIT_SESSION_FILE=data/fast_session.json
X_SESSION_FILE=data/x_session.json
X_USERNAME=mottoappraisal
X_PASSWORD=
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=luke-motto
OLLAMA_FALLBACK_MODEL=llama3.1:8b
PLAYWRIGHT_DEBUG=0
BROWSER_HEADFUL=0
EOF
    echo "  .env written. Add GMAIL_APP_PASSWORD if blank."
fi

# ── 6. Warm up Ollama ─────────────────────────────────────────────
echo "[6/7] Warming up Ollama..."

# Pull base model
echo "  Pulling llama3.1:8b (this may take a few minutes)..."
ollama pull llama3.1:8b 2>&1 || {
    echo "  ⚠ Ollama pull failed — check if Ollama is running (ollama serve)"
}

# Run sharpener to build the luke-motto model
echo "  Building luke-motto persona model..."
source "$INSTALL_DIR/venv/bin/activate"
cd "$INSTALL_DIR"
python3 sharpener.py 2>&1 || echo "  ⚠ Sharpener first run warning (OK if no send logs yet)"

echo "  Ollama model list:"
ollama list 2>/dev/null || echo "  (ollama list failed)"

# ── 7. Install cron jobs ──────────────────────────────────────────
echo "[7/7] Installing cron jobs..."

# Remove existing motto-outreach crons (idempotent)
crontab -l 2>/dev/null | grep -v "motto-outreach" > /tmp/crontab_current || true

# 2-hour cycle: runs at :05 past every even hour (CDT = UTC-5)
# UTC 05:05, 07:05, 09:05, 11:05, 13:05, 15:05, 17:05, 19:05, 21:05, 23:05, 01:05, 03:05
CYCLE_CRON="5 1,3,5,7,9,11,13,15,17,19,21,23 * * * cd $INSTALL_DIR && bash run.sh cycle >> $LOG_DIR/cron.log 2>&1"

# Daily sharpener: 6:00 AM CDT = 11:00 UTC
SHARPEN_CRON="0 11 * * * cd $INSTALL_DIR && bash run.sh sharpen >> $LOG_DIR/sharpener_cron.log 2>&1"

cat >> /tmp/crontab_current <<EOF

# motto-outreach — 2-hour cycle
$CYCLE_CRON

# motto-outreach — daily sharpener at 6am CDT
$SHARPEN_CRON
EOF

crontab /tmp/crontab_current
echo "  ✓ Cron jobs installed"

echo ""
echo "  Active crons:"
crontab -l | grep -E "motto-outreach|outreach" || echo "  (none found — check above for errors)"

# ── Dry run validation ────────────────────────────────────────────
echo ""
echo "========================================"
echo " Running validation dry-run..."
echo "========================================"
cd "$INSTALL_DIR"
source venv/bin/activate
python3 agent.py --dry-run 2>&1 | tail -30

echo ""
echo "========================================"
echo " Setup complete!"
echo ""
echo " Next steps:"
echo "  1. Check .env has GMAIL_APP_PASSWORD filled in"
echo "  2. Verify Reddit session: cat data/fast_session.json"
echo "  3. Optionally set up X session: python3 x_client.py --login"
echo "  4. View live logs: tail -f logs/outreach_$(date +%Y-%m-%d).log"
echo "  5. First real cycle runs at next even hour (:05 past)"
echo "========================================"
