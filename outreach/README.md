# Motto Outreach Agent

Autonomous Reddit + X outreach system for Motto Appraisal Service.
Runs on DigitalOcean droplet (138.197.2.28) every 2 hours.

## Architecture

```
agent.py          ← Main cron entrypoint (2-hour cycle)
sharpener.py      ← Daily Ollama improvement loop
abcd.py           ← Thompson Sampling ABCD variant tracker
ollama_client.py  ← Free inference via Ollama (luke-motto model)
reddit_client.py  ← Playwright Reddit DM + comment sender
x_client.py       ← Playwright X reply automation
reporter.py       ← Email digest (SMTP via Gmail)
run.sh            ← Cron wrapper with lock guard
cron_setup.sh     ← Full droplet install script
```

## Ramp Schedule (account safety)

| Days Running | Reddit DMs | Reddit Comments | X Replies |
|---|---|---|---|
| 1-3   | 5  | 5  | 8  |
| 4-7   | 10 | 8  | 15 |
| 8-14  | 15 | 12 | 20 |
| 15+   | 20 | 15 | 25 |

## ABCD Variants (Thompson Sampling)

- **A** — Direct professional: "I'm a licensed DFW appraiser..."
- **B** — Data-led: leads with a market data point
- **C** — Problem-first: addresses their stated problem first
- **D** — Purely helpful: adds genuine value, no pitch

## Ollama Sharpener

The daily sharpener (6am CDT) reads the last 48h of send logs,
analyzes patterns, and updates the `luke-motto` Ollama model's
system prompt with new lessons. This creates a compounding improvement
loop — each day's outreach is smarter than the last.

## Deploy

```bash
# On droplet:
git clone https://github.com/lkmotto/motto-outreach.git /opt/motto-outreach
cd /opt/motto-outreach
export GMAIL_APP_PASSWORD="your-app-password"
bash cron_setup.sh
```

## Manual Commands

```bash
# Check status
bash run.sh status

# Dry run (scan, don't send)
bash run.sh dry

# Run one live cycle now
bash run.sh cycle

# Run sharpener manually
bash run.sh sharpen

# Watch live logs
tail -f logs/outreach_$(date +%Y-%m-%d).log
```

## Session Files

- `data/fast_session.json` — Reddit session cookie (valid Oct 2026)
- `data/x_session.json` — X session (create via `python3 x_client.py --login`)
- `data/state.json` — Running state (DM counts, seen IDs, sent_to list)
- `data/abcd_state.json` — Thompson Sampling posteriors
- `data/ollama_persona.txt` — Evolving Ollama system prompt

## Email Reports

Reports sent to `ljm32901@gmail.com` after every cycle that sends
at least one communication. Reports include:
- What was sent this cycle
- Running ABCD variant stats
- Any replies received in inbox
- Suggested responses to replies
