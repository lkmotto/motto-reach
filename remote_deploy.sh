#!/usr/bin/env bash
# remote_deploy.sh — Run this ONCE on the DigitalOcean droplet (138.197.2.28)
# as root. It installs everything from scratch.
#
# Copy-paste command:
#   curl -fsSL https://raw.githubusercontent.com/lkmotto/motto-outreach/main/remote_deploy.sh | bash
#
# OR if the repo is private (it is), run:
#   bash /tmp/remote_deploy.sh
# after uploading with:
#   scp remote_deploy.sh root@138.197.2.28:/tmp/

set -euo pipefail

INSTALL_DIR="/opt/motto-outreach"
REPO_URL="https://github.com/lkmotto/motto-outreach.git"
GITHUB_USER="lkmotto"
LOG_FILE="/tmp/deploy_$(date +%Y%m%d_%H%M%S).log"

# ─── Logging ─────────────────────────────────────────────────────────
exec > >(tee -a "$LOG_FILE") 2>&1
echo "============================================"
echo " Motto Outreach — Remote Deploy"
echo " $(date)"
echo "============================================"

# ─── 1. System deps ──────────────────────────────────────────────────
echo ""
echo "[1/8] System packages..."
apt-get update -qq
apt-get install -y -qq git python3 python3-pip python3-venv curl wget \
    chromium-browser \
    fonts-liberation libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 2>/dev/null || \
apt-get install -y -qq git python3 python3-pip python3-venv curl wget \
    chromium libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 2>/dev/null || true
echo "  ✓ System packages"

# ─── 2. Install Ollama ────────────────────────────────────────────────
echo ""
echo "[2/8] Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    # Start as service or background process
    if systemctl list-unit-files ollama.service &>/dev/null; then
        systemctl enable ollama 2>/dev/null || true
        systemctl start ollama 2>/dev/null || true
    else
        nohup ollama serve > /tmp/ollama.log 2>&1 &
    fi
    sleep 5
    echo "  ✓ Ollama installed"
else
    echo "  ✓ Ollama already installed"
    # Ensure it's running
    ollama list &>/dev/null || (nohup ollama serve > /tmp/ollama.log 2>&1 & sleep 3)
fi

# ─── 3. Clone / update repo ───────────────────────────────────────────
echo ""
echo "[3/8] Cloning repo..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Updating existing repo..."
    cd "$INSTALL_DIR"
    git fetch origin
    git reset --hard origin/main
    git pull origin main
else
    echo "  Cloning fresh..."
    mkdir -p "$(dirname $INSTALL_DIR)"
    # Private repo — needs token or SSH key
    # If GITHUB_PAT is set, use it:
    if [ -n "${GITHUB_PAT:-}" ]; then
        git clone "https://${GITHUB_PAT}@github.com/${GITHUB_USER}/motto-outreach.git" "$INSTALL_DIR"
    else
        echo ""
        echo "  ⚠ Private repo requires GITHUB_PAT env var."
        echo "  Set it before running: export GITHUB_PAT=your_pat_here"
        echo "  Or run: GITHUB_PAT=ghp_xxx bash remote_deploy.sh"
        exit 1
    fi
fi
cd "$INSTALL_DIR"
echo "  ✓ Repo at $INSTALL_DIR"

# ─── 4. Python venv + packages ────────────────────────────────────────
echo ""
echo "[4/8] Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
# Install Playwright Chromium
python3 -m playwright install chromium --with-deps 2>&1 | tail -5
echo "  ✓ Python packages + Playwright"

# ─── 5. Session files ─────────────────────────────────────────────────
echo ""
echo "[5/8] Session files..."
mkdir -p data logs

# fast_session.json must be uploaded separately (not in git for security)
if [ ! -f "data/fast_session.json" ]; then
    echo "  ⚠ Reddit session not found."
    echo "  Upload it with:"
    echo "    scp /home/user/workspace/motto-reddit/fast_session.json root@138.197.2.28:$INSTALL_DIR/data/"
else
    echo "  ✓ Reddit session present"
fi

# x_session.json placeholder
if [ ! -f "data/x_session.json" ]; then
    echo '{}' > data/x_session.json
    echo "  ✓ X session placeholder created (run --login to populate)"
fi

# ─── 6. Write .env ────────────────────────────────────────────────────
echo ""
echo "[6/8] Environment file..."
if [ ! -f ".env" ]; then
    GMAIL_PASS="${GMAIL_APP_PASSWORD:-}"
    cat > .env <<EOF
GMAIL_APP_PASSWORD=${GMAIL_PASS}
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
    echo "  .env written — add GMAIL_APP_PASSWORD if blank"
else
    echo "  .env already exists"
fi

# ─── 7. Pull base model + build luke-motto ────────────────────────────
echo ""
echo "[7/8] Pulling Ollama base model (llama3.1:8b)..."
echo "  This takes 5-10 min on first run..."
ollama pull llama3.1:8b 2>&1 | tail -3

echo "  Building luke-motto persona model..."
source venv/bin/activate
python3 sharpener.py || echo "  (First sharpener run — OK if no send logs)"

echo "  Installed Ollama models:"
ollama list

# ─── 8. Install cron jobs ─────────────────────────────────────────────
echo ""
echo "[8/8] Cron jobs..."

# Remove existing motto-outreach crons
crontab -l 2>/dev/null | grep -v "motto-outreach" > /tmp/crontab_new || true

cat >> /tmp/crontab_new <<EOF

# motto-outreach — 2-hour outreach cycle
5 1,3,5,7,9,11,13,15,17,19,21,23 * * * cd $INSTALL_DIR && bash run.sh cycle >> $INSTALL_DIR/logs/cron.log 2>&1

# motto-outreach — daily sharpener at 6am CDT (11:00 UTC)
0 11 * * * cd $INSTALL_DIR && bash run.sh sharpen >> $INSTALL_DIR/logs/sharpener_cron.log 2>&1
EOF

crontab /tmp/crontab_new
echo "  ✓ Cron jobs installed"
echo ""
echo "  Active motto crons:"
crontab -l | grep motto-outreach

# ─── Validation dry run ───────────────────────────────────────────────
echo ""
echo "============================================"
echo " Validation dry-run..."
echo "============================================"
source venv/bin/activate
python3 agent.py --dry-run 2>&1 | tail -40

echo ""
echo "============================================"
echo " Deploy complete!  $(date)"
echo ""
echo " Reddit session : $([ -f data/fast_session.json ] && echo '✓ Present' || echo '✗ MISSING — upload needed')"
echo " Ollama models  : $(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ', ')"
echo " Crons active   : $(crontab -l | grep -c motto-outreach || echo 0)"
echo ""
echo " Log: $LOG_FILE"
echo " Watch live: tail -f $INSTALL_DIR/logs/outreach_$(date +%Y-%m-%d).log"
echo "============================================"
