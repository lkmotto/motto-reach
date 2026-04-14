#!/usr/bin/env bash
# bootstrap_droplet.sh — All-in-one droplet bootstrap
# This script does NOT need git credentials.
# Usage: bash bootstrap_droplet.sh
# Run as root on: 138.197.2.28

set -euo pipefail
echo "=== Motto Outreach Bootstrap ==="

# ── 1. System deps ─────────────────────────────────────────────────────
apt-get update -qq 2>/dev/null
apt-get install -y -qq python3 python3-pip python3-venv git curl wget 2>/dev/null

# ── 2. Ollama ──────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 5
else
    echo "Ollama already installed"
    ollama list &>/dev/null || (nohup ollama serve > /tmp/ollama.log 2>&1 & sleep 3)
fi

# ── 3. Create directory structure ──────────────────────────────────────
mkdir -p /opt/motto-outreach/data /opt/motto-outreach/logs
cd /opt/motto-outreach

# ── 4. Write Reddit session (embedded) ────────────────────────────────
echo "Writing Reddit session..."
echo "WwogIHsKICAgICJuYW1lIjogInJlZGRpdF9zZXNzaW9uIiwKICAgICJ2YWx1ZSI6ICJleUpoYkdjaU9pSlNVekkxTmlJc0ltdHBaQ0k2SWxOSVFUSTFOanBzVkZkWU5sRlZVRWxvV2t0YVJHMXJSMHBWZDFndmRXTkZLMDFCU2pCWVJFMTJSVTFrTnpWeFRYUTRJaXdpZEhsd0lqb2lTbGRVSW4wLmV5SnpkV0lpT2lKME1sOHhkWEIwTjNOMFp6SnRJaXdpWlhod0lqb3hOemt4TnpVNU1UZzRMamMyTURReE1Td2lhV0YwSWpveE56YzJNVEl3TnpnNExqYzJNRFF4TVN3aWFuUnBJam9pV0dwemNYaE5UVmRJVWsxak1sOXpOVW95UVRGdk0ybEtXRkY1VUZGQklpd2lZWFFpT2pFc0ltTnBaQ0k2SW1OdmIydHBaU0lzSW14allTSTZNVGMxTXprNU1Ua3lNVEF4Tml3aWMyTndJam9pWlVwNVMycG5WVVZCUVVSZlgzZEZWa0ZNYXlJc0ltWnNieUk2TWl3aVlXMXlJanBiSW5CM1pDSmRmUS5sb0R5MFpTNVJSUXFEMHlyNklMSXQ3U1ZPWjh0XzhVbmNOVlZ4Mk5ERVRmblk3WlB4Wm1yX1JXX20wbmxQc2F2VkFTbGduNlk0bFlpTnJrbk5TNWlqVXEzZ1FhUnhWZzJaa29qQXF1SVlBTTh5QlVMQTQ5QnFGdGMtZEpZS0V4NEY2R3BqT0U5SXNGNGxWeUVGaWxxZVZVVmpMaVRVdDRiMmJHVG9sRXNtSG9Rbmk2RWtiSkU1aWE5ZU8tc1NKTmRsX25FRTd3X3JiSV9FNGdYMFlMUFBFSS1xZGxHVWZNTzRyMWctblZfc3g4MmdqaEtYWFk0NDJaSHU2VWh6VmNLaXVzVkFXQlZYT0E3WVplSzdyMXNScHhMWGJ2V3hqbkpSOTNnT25MTndnWjUzM0F4QmlVV21KTGdTVjktSFA1V3FiYTdLM3JuY3FWb19ZR3JkZ0NpeGciLAogICAgImRvbWFpbiI6ICIucmVkZGl0LmNvbSIsCiAgICAicGF0aCI6ICIvIiwKICAgICJodHRwT25seSI6IHRydWUsCiAgICAic2VjdXJlIjogdHJ1ZSwKICAgICJzYW1lU2l0ZSI6ICJMYXgiCiAgfQpd" | base64 -d > data/fast_session.json
echo '{}' > data/x_session.json
echo "Session written: $(wc -c < data/fast_session.json) bytes"

# ── 5. Pull source files from GitHub (public archive) ─────────────────
# Using the GitHub API to download individual files without auth
# (works on private repos ONLY if GITHUB_PAT is set, otherwise fails gracefully)
GITHUB_PAT="${GITHUB_PAT:-}"
REPO="lkmotto/motto-outreach"
BRANCH="main"

download_file() {
    local filepath="$1"
    local dest="$2"
    if [ -n "$GITHUB_PAT" ]; then
        curl -fsSL "https://raw.githubusercontent.com/${REPO}/${BRANCH}/${filepath}"             -H "Authorization: token $GITHUB_PAT" -o "$dest"
    else
        curl -fsSL "https://raw.githubusercontent.com/${REPO}/${BRANCH}/${filepath}"             -o "$dest" 2>/dev/null
    fi
}

FILES="agent.py abcd.py ollama_client.py reddit_client.py x_client.py reporter.py sharpener.py run.sh requirements.txt .env.example"

echo "Downloading source files..."
for f in $FILES; do
    download_file "$f" "/opt/motto-outreach/$f" && echo "  ✓ $f" || echo "  ✗ $f (private — needs GITHUB_PAT)"
done

# Download data files
download_file "data/state.json"      "data/state.json"
download_file "data/abcd_state.json" "data/abcd_state.json"

chmod +x run.sh

# ── 6. .env file ───────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    GMAIL_PASS="${GMAIL_APP_PASSWORD:-}"
    cat > .env <<EOF
GMAIL_APP_PASSWORD=${GMAIL_PASS}
REPORT_TO_EMAIL=ljm32901@gmail.com
REPORT_FROM_EMAIL=ljm32901@gmail.com
REDDIT_SESSION_FILE=data/fast_session.json
X_SESSION_FILE=data/x_session.json
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=luke-motto
OLLAMA_FALLBACK_MODEL=llama3.1:8b
PLAYWRIGHT_DEBUG=0
BROWSER_HEADFUL=0
EOF
    echo ".env written — fill in GMAIL_APP_PASSWORD if needed"
fi

# ── 7. Python venv ─────────────────────────────────────────────────────
echo "Setting up Python..."
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet playwright requests python-dotenv
python3 -m playwright install chromium --with-deps 2>&1 | tail -3

# ── 8. Ollama model ────────────────────────────────────────────────────
echo "Pulling Ollama base model (llama3.1:8b — may take 5 min)..."
ollama pull llama3.1:8b 2>&1 | tail -3

echo "Building luke-motto persona..."
source venv/bin/activate
python3 sharpener.py 2>&1 | tail -5

# ── 9. Cron ────────────────────────────────────────────────────────────
echo "Installing cron jobs..."
crontab -l 2>/dev/null | grep -v "motto-outreach" > /tmp/ct || true
cat >> /tmp/ct <<CRON

# motto-outreach cycle every 2h
5 1,3,5,7,9,11,13,15,17,19,21,23 * * * cd /opt/motto-outreach && bash run.sh cycle >> logs/cron.log 2>&1

# motto-outreach daily sharpener 6am CDT (11 UTC)
0 11 * * * cd /opt/motto-outreach && bash run.sh sharpen >> logs/sharpener_cron.log 2>&1
CRON
crontab /tmp/ct
echo "Crons installed:"
crontab -l | grep motto-outreach

# ── 10. Validation ─────────────────────────────────────────────────────
echo ""
echo "=== Validation dry-run ==="
source venv/bin/activate
python3 agent.py --dry-run 2>&1 | tail -30

echo ""
echo "=== Bootstrap complete ==="
echo "Reddit session: $([ -f data/fast_session.json ] && echo 'OK' || echo 'MISSING')"
echo "Ollama models: $(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ', ')"
echo "Crons: $(crontab -l | grep -c motto-outreach || echo 0) jobs active"
echo "Next cycle: next odd hour :05 (e.g. 9:05pm, 11:05pm CDT)"
