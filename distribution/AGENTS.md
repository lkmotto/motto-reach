# AGENTS.md

> Operational spec for autonomous coding agents (Factory Droid, Codex, Cursor, Aider). Human-readable too.

## Identity
- **Repo:** `lkmotto/motto-distribution`
- **Purpose:** Multi-platform content distribution engine that transforms a LinkedIn post into platform-native content for X, Beehiiv, Medium, Substack, Reddit, Facebook Groups, LinkedIn Groups, cold outreach, and SMS.
- **Status:** Dark since 2026-04-06 — references Maritime (dead platform); not actively deployed
- **Owner:** Luke Motto (`ljm32901@gmail.com`)
- **Linear team:** Mottoappraisal (MOT) · project Fleet Operations

## What this code does
Takes a LinkedIn post dict as input, runs it through a rule-based classifier, generates 21 platform-native sections via Claude Sonnet, auto-posts to X (gated), drafts to Beehiiv, and queues everything else for manual review. Tracks token costs per section and appends results to a local JSON run log. Was deployed to Maritime Smart tier before Maritime shut down.

## Architecture at a glance
- `tools/classifier.py` — Rule-based content classification (no API calls)
- `tools/transformer.py` — Claude `claude-sonnet-4-5` generation for all 21 sections
- `tools/x_poster.py` — X OAuth1.0a posting (consumer key/secret + access token pair)
- `tools/beehiiv_publisher.py` — Beehiiv newsletter draft creation
- `tools/queue.py` — Local JSON content queue state
- `agent/distributor.py` — Main orchestrator; calls all tools in sequence
- `maritime.toml` — Maritime deployment config (dead — do not use)
- `cron_tracking/` — Queue state, run log, per-run result JSONs

## Runtime
- **Language/runtime:** Python 3.x
- **Entry point:** `python -m agent.distributor` or Maritime webhook (defunct)
- **Hosting:** Not actively deployed — Maritime is dead. No Northflank config.
- **Schedule:** Was webhook-triggered; no cron

## Required environment variables
| Variable | Purpose | Source |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude Sonnet for all content generation | Doppler `motto-core/prd` |
| `BEEHIIV_API_KEY` | Beehiiv newsletter draft creation | Doppler `motto-core/prd` |
| `AUTO_POST_X` | Safety gate for X auto-posting (`true` to enable) | Northflank env |
| `POST_TO_COMPANY_PAGE` | Auto-post to LinkedIn company page (`true` to enable) | Northflank env |
| `REDDIT_AUTO_POST` | Safety gate for Reddit posting (default `false`) | Northflank env |
| `REDDIT_CLIENT_ID` | Reddit PRAW app credentials | Doppler `motto-core/prd` |
| `REDDIT_CLIENT_SECRET` | Reddit PRAW app credentials | Doppler `motto-core/prd` |
| `REDDIT_USERNAME` | Reddit account (`Opposite_Ground594`) | Doppler `motto-core/prd` |
| `REDDIT_PASSWORD` | Reddit account password | Doppler `motto-core/prd` |
| `FACEBOOK_GROUPS_TOKEN` | Facebook personal token for group posting | Doppler `motto-core/prd` |
| `CTA_URL` | Override default CTA URL (optional) | Northflank env |

## Doppler config
- Project: `motto-core`
- Config: `prd`
- Pull command: `doppler run --project motto-core --config prd -- <command>`

## How to run locally
```bash
pip install anthropic requests
cp .env.example .env   # fill in values
# X credentials loaded from JSON files (see .env.example for paths)
python -m agent.distributor
```

## How to deploy
No active deploy pipeline. Maritime is dead. To revive: port to Northflank, remove `maritime.toml`, update deploy config. See `motto-social-agent` for the active social posting agent.

## Conventions
- Branch from `main`. PRs only. No direct pushes to main.
- Use DeepSeek V4 / Reasoner for code generation. Claude is banned from this fleet for cost reasons.
- One PR per logical change. Keep diffs minimal.
- Update this AGENTS.md if you change the architecture.

## Known issues / open loops
- X credentials stored as JSON files (not env vars) — paths: `/home/user/workspace/credentials/x_user_token.json` and `x_oauth.json`. Ensure these are mounted correctly if containerizing.
- All Reddit posts flagged `manual_review_required=True` regardless of `REDDIT_AUTO_POST`.
- `AUTO_POST_X` must be `true` AND `auto_post_x=True` in the call for X posts to send.
- Review if this repo should be retired in favor of `motto-social-agent`.

## Maritime status
Maritime.sh is dead. `maritime.toml` in this repo is cruft to remove (see Linear MOT-8…MOT-13 for parallel scrub tickets).
