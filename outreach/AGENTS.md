# AGENTS.md

> Operational spec for autonomous coding agents (Factory Droid, Codex, Cursor, Aider). Human-readable too.

## Identity
- **Repo:** `lkmotto/motto-outreach`
- **Purpose:** Autonomous Reddit + X outreach agent that sends DMs, comments, and replies using Thompson Sampling (ABCD) variant testing and a daily Ollama self-improvement loop.
- **Status:** Active on DigitalOcean droplet — last commit 2026-04-14; runs via cron on droplet IP 138.197.2.28
- **Owner:** Luke Motto (`ljm32901@gmail.com`)
- **Linear team:** Mottoappraisal (MOT) · project Fleet Operations

## What this code does
Every 2 hours, the agent scans Reddit and X for appraisal-related conversations, selects message variants using Thompson Sampling (A: direct professional, B: data-led, C: problem-first, D: purely helpful), and sends DMs/comments/replies via Playwright browser automation with a ramp schedule for account safety. A daily 6am sharpener reads 48h of send logs and refines the `luke-motto` Ollama model's system prompt. Gmail digest reports sent after each cycle.

## Architecture at a glance
- `agent.py` — Main 2-hour cron entrypoint; orchestrates all channels
- `sharpener.py` — Daily Ollama improvement loop; updates evolving system prompt
- `abcd.py` — Thompson Sampling ABCD variant tracker
- `ollama_client.py` — Local Ollama inference (`luke-motto` model built from `llama3.1:8b`)
- `reddit_client.py` — Playwright Reddit DM + comment automation
- `x_client.py` — Playwright X reply automation
- `reporter.py` — SMTP email digest via Gmail
- `run.sh` — Cron wrapper with lock guard
- `data/` — Session cookies, state JSON, ABCD posteriors, Ollama persona

## Runtime
- **Language/runtime:** Python 3.x + Playwright
- **Entry point:** `bash run.sh cycle` (one live cycle) or via cron every 2h
- **Hosting:** DigitalOcean droplet at 138.197.2.28 (`/opt/motto-outreach/`)
- **Schedule:** Every 2 hours via cron (`run.sh`); sharpener daily at 6am CDT

## Required environment variables
| Variable | Purpose | Source |
|---|---|---|
| `GMAIL_APP_PASSWORD` | Gmail app password for SMTP email reports | Droplet `.env` |
| `REPORT_TO_EMAIL` | Email to receive digest reports (`ljm32901@gmail.com`) | Droplet `.env` |
| `REPORT_FROM_EMAIL` | Gmail send-from address | Droplet `.env` |
| `REDDIT_SESSION_FILE` | Path to Reddit session cookie JSON (valid Oct 2026) | Droplet `.env` |
| `X_SESSION_FILE` | Path to X session JSON | Droplet `.env` |
| `X_USERNAME` | X account username (`mottoappraisal`) | Droplet `.env` |
| `X_PASSWORD` | X account password (for session refresh) | Droplet `.env` |
| `OLLAMA_URL` | Ollama instance URL (`http://localhost:11434`) | Droplet `.env` |
| `OLLAMA_MODEL` | Ollama model name (`luke-motto`) | Droplet `.env` |
| `OLLAMA_FALLBACK_MODEL` | Fallback model (`llama3.1:8b`) | Droplet `.env` |
| `TELEGRAM_BOT_TOKEN` | Fleet reporting (optional) | Droplet `.env` |
| `TELEGRAM_CHAT_ID` | Fleet chat ID (optional) | Droplet `.env` |

## Doppler config
- Project: `motto-core`
- Config: `prd`
- Pull command: `doppler run --project motto-core --config prd -- <command>`

## How to run locally
```bash
# On droplet:
bash run.sh dry      # dry run (scan, don't send)
bash run.sh cycle    # one live cycle
bash run.sh sharpen  # run sharpener manually
bash run.sh status   # check status
tail -f logs/outreach_$(date +%Y-%m-%d).log
```

## How to deploy
```bash
# On droplet at 138.197.2.28:
git clone https://github.com/lkmotto/motto-outreach.git /opt/motto-outreach
cd /opt/motto-outreach
export GMAIL_APP_PASSWORD="your-app-password"
bash cron_setup.sh   # installs cron, Ollama, Python deps
```

## Conventions
- Branch from `main`. PRs only. No direct pushes to main.
- Use DeepSeek V4 / Reasoner for code generation. Claude is banned from this fleet for cost reasons.
- One PR per logical change. Keep diffs minimal.
- Update this AGENTS.md if you change the architecture.

## Known issues / open loops
- Reddit session (`data/fast_session.json`) valid until October 2026 — plan renewal.
- X session (`data/x_session.json`) — expiry unknown; refresh via `python3 x_client.py --login` if broken.
- `bootstrap_droplet.sh` embeds Reddit session — do not regenerate without updating this file.
- No Northflank or container deploy — lives on bare droplet. Shared with `motto-sharpener` (same IP).

## Maritime status
Maritime.sh is dead. This repo does not reference Maritime.
