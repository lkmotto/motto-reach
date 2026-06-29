"""
sharpener.py — Daily Ollama improvement loop
Runs once per day at 6am CDT. Reads last 48h of send logs, analyzes
ABCD variant performance, and updates the Ollama model's system prompt
with lessons learned so each day's outreach is smarter than the last.

Usage: python3 sharpener.py
Cron:  0 11 * * * cd /opt/motto-outreach && python3 sharpener.py
"""
from motto_common.sentry_init import init_sentry  # was: import sentry_init
init_sentry(agent_name="motto-outreach")

import json
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE       = Path(__file__).parent
LOG_DIR    = BASE / "logs"
DATA_DIR   = BASE / "data"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

today_str = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sharpener] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"sharpener_{today_str}.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("sharpener")

SHARPENER_LOG  = DATA_DIR / "sharpener_log.jsonl"
PROMPT_LOG     = DATA_DIR / "prompt_evolution.jsonl"
OLLAMA_PERSONA = DATA_DIR / "ollama_persona.txt"

# ─────────────────────────────────────────────────────────────────────
# Load recent sends
# ─────────────────────────────────────────────────────────────────────

def load_recent_sends(max_files: int = 2) -> list:
    """Load JSONL send logs from the last N days."""
    sends = []
    log_files = sorted(LOG_DIR.glob("sends_*.jsonl"))[-max_files:]
    for lf in log_files:
        with open(lf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    sends.append(json.loads(line))
                except Exception:
                    pass
    return sends


def load_abcd_state() -> dict:
    """Read current ABCD variant stats."""
    abcd_file = DATA_DIR / "abcd_state.json"
    if abcd_file.exists():
        try:
            return json.loads(abcd_file.read_text())
        except Exception:
            pass
    return {}


# ─────────────────────────────────────────────────────────────────────
# Core analysis via Ollama
# ─────────────────────────────────────────────────────────────────────

def analyze_and_sharpen(sends: list, abcd_state: dict) -> dict | None:
    """
    Feed send history to Ollama and extract:
    1. Which variant style performed best
    2. Patterns in high-engagement posts
    3. Suggested prompt improvement for tomorrow
    """
    try:
        from ollama_client import sharpen as ollama_sharpen
        analysis = ollama_sharpen(sends)
        if not analysis:
            log.warning("Ollama returned empty sharpener analysis")
            return None
        return analysis
    except ImportError:
        log.error("ollama_client not found")
        return None
    except Exception as e:
        log.error(f"Sharpener Ollama call failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# Prompt evolution: update the Ollama persona with new lessons
# ─────────────────────────────────────────────────────────────────────

BASE_PERSONA = """You are Luke Motto, a licensed residential real estate appraiser in DFW, Texas.
You are authentic, direct, and genuinely helpful. You never spam people.
Your goal is to naturally enter real estate conversations and offer real value,
occasionally mentioning your appraisal services when it's clearly relevant.

Background:
- Licensed Texas Certified Residential Appraiser
- Based in Trophy Club, TX 76262
- Phone: (817) 217-4375
- Specialties: SFR appraisals, DSCR investor appraisals, divorce/estate appraisals
- DFW market expert: median SFR $375K-$425K, 33K+ listings, 35-55 DOM avg

Communication principles:
- Be the helpful neighbor, not the pushy salesman
- Lead with value: data, insight, or a specific answer to their question
- Only mention your services if they have a clear appraisal need
- Keep DMs short (3-5 sentences max)
- Comments should add real value to the thread, not just advertise
- Never use phrases like "I'd be happy to help!" — be direct and specific
- Match the casual tone of Reddit/X; don't sound like a corporate email
"""

def update_persona(analysis: dict) -> str:
    """Append learned lessons to the persona file."""
    try:
        if OLLAMA_PERSONA.exists():
            current = OLLAMA_PERSONA.read_text()
        else:
            current = BASE_PERSONA

        lessons = analysis.get("lessons", [])
        if not lessons:
            log.info("No new lessons to append to persona")
            return current

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lesson_block = f"\n\n# Lessons learned {timestamp}:\n"
        for i, lesson in enumerate(lessons[:5], 1):
            lesson_block += f"{i}. {lesson}\n"

        updated = current + lesson_block

        # Keep persona from bloating — trim old lessons beyond 500 lines
        lines = updated.split("\n")
        if len(lines) > 500:
            # Keep base persona + last 200 lesson lines
            base_end = BASE_PERSONA.count("\n") + 5
            updated = "\n".join(lines[:base_end] + lines[-200:])

        OLLAMA_PERSONA.write_text(updated)
        log.info(f"Persona updated with {len(lessons)} lessons")

        # Log this evolution
        with open(PROMPT_LOG, "a") as f:
            f.write(json.dumps({
                "date": timestamp,
                "lessons": lessons,
                "analysis_snippet": analysis.get("analysis", "")[:300],
            }) + "\n")

        return updated

    except Exception as e:
        log.error(f"Persona update failed: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────
# Ollama Modelfile rebuild (re-trains custom model with updated persona)
# ─────────────────────────────────────────────────────────────────────

def rebuild_ollama_model(persona_text: str):
    """
    Rebuild the luke-motto Ollama model with the updated system prompt.
    Runs: ollama create luke-motto -f /opt/motto-outreach/data/Modelfile
    """
    import subprocess

    modelfile_path = DATA_DIR / "Modelfile"
    modelfile_text = f"""FROM llama3.1:8b

SYSTEM \"\"\"{persona_text.strip()}\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_predict 256
"""
    modelfile_path.write_text(modelfile_text)
    log.info("Modelfile written")

    try:
        result = subprocess.run(
            ["ollama", "create", "luke-motto", "-f", str(modelfile_path)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log.info("Ollama model 'luke-motto' rebuilt successfully")
        else:
            log.error(f"Ollama create failed: {result.stderr[:300]}")
    except FileNotFoundError:
        log.warning("ollama binary not found — model rebuild skipped (running without Ollama)")
    except subprocess.TimeoutExpired:
        log.warning("Ollama create timed out after 120s — may still be building")
    except Exception as e:
        log.error(f"Ollama rebuild error: {e}")


# ─────────────────────────────────────────────────────────────────────
# ABCD feedback loop: adjust priors based on send outcomes
# ─────────────────────────────────────────────────────────────────────

def abcd_feedback(sends: list):
    """
    Infer variant outcomes from send logs:
    - 'reply' field presence → treat as positive outcome
    - Adjust Thompson Sampling priors in abcd_state.json
    """
    try:
        from abcd import record_reply, get_status
        replies_found = 0
        for send in sends:
            # If the JSONL contains a 'got_reply' flag (set by inbox checker)
            if send.get("got_reply") and send.get("variant"):
                record_reply(send["variant"], send.get("channel", "dm"))
                replies_found += 1

        if replies_found > 0:
            log.info(f"ABCD feedback: recorded {replies_found} positive outcomes")
        else:
            log.info("ABCD feedback: no confirmed replies in log — posteriors unchanged")

    except ImportError:
        log.warning("abcd module not available for feedback")
    except Exception as e:
        log.error(f"ABCD feedback error: {e}")


# ─────────────────────────────────────────────────────────────────────
# Stats report helper
# ─────────────────────────────────────────────────────────────────────

def print_stats(sends: list, abcd_state: dict):
    """Print a human-readable summary to stdout/log."""
    total   = len(sends)
    dms     = sum(1 for s in sends if s.get("dm_sent"))
    comments = sum(1 for s in sends if s.get("comment_sent"))
    x_sent  = sum(1 for s in sends if s.get("type") == "x_reply" and s.get("sent"))
    replies  = sum(1 for s in sends if s.get("got_reply"))

    log.info("="*50)
    log.info(f"48-hour stats  —  {today_str}")
    log.info(f"  Total actions : {total}")
    log.info(f"  Reddit DMs    : {dms}")
    log.info(f"  Reddit comments: {comments}")
    log.info(f"  X replies     : {x_sent}")
    log.info(f"  Replies received: {replies}")

    # ABCD summary
    for channel, variants in abcd_state.items():
        log.info(f"  ABCD [{channel}]:")
        for var_id, v in variants.items():
            alpha = v.get("alpha", 1)
            beta  = v.get("beta", 1)
            mean  = alpha / (alpha + beta)
            log.info(f"    Variant {var_id}: α={alpha} β={beta} → mean={mean:.2%}")

    log.info("="*50)


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main():
    log.info("Sharpener starting...")

    sends = load_recent_sends(max_files=2)
    abcd_state = load_abcd_state()

    print_stats(sends, abcd_state)

    if len(sends) < 3:
        log.info(f"Only {len(sends)} sends in log — skipping LLM analysis (need ≥3)")
        # Still rebuild model with base persona if no custom one exists
        if not OLLAMA_PERSONA.exists():
            OLLAMA_PERSONA.write_text(BASE_PERSONA)
            rebuild_ollama_model(BASE_PERSONA)
        log.info("Sharpener done (no analysis needed yet)")
        return

    # Run ABCD feedback pass first
    abcd_feedback(sends)

    # Run LLM analysis
    log.info("Running Ollama analysis...")
    analysis = analyze_and_sharpen(sends, abcd_state)

    if not analysis:
        log.warning("Analysis failed — persona unchanged")
        return

    # Persist analysis
    with open(SHARPENER_LOG, "a") as f:
        f.write(json.dumps({
            "date": today_str,
            "sends_analyzed": len(sends),
            **analysis
        }) + "\n")

    log.info(f"Analysis: {analysis.get('analysis', '')[:200]}")

    # Update persona + rebuild model
    updated_persona = update_persona(analysis)
    if updated_persona:
        rebuild_ollama_model(updated_persona)

    log.info("Sharpener complete.")


if __name__ == "__main__":
    import sentry_sdk as _sentry_sdk
    try:
        main()
    except Exception as _exc:
        _sentry_sdk.capture_exception(_exc)
        raise

