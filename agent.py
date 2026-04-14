"""
agent.py — Main 2-hour cron entrypoint
Scans Reddit + X, drafts via Ollama, sends with ABCD variants, reports by email.

Usage: python3 agent.py --cycle
Cron:  0 */2 * * * cd /opt/motto-outreach && python3 agent.py --cycle
"""
import os, sys, json, time, random, logging, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── Paths ─────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent
STATE_FILE = BASE / "data" / "state.json"
QUEUE_FILE = BASE / "data" / "queue.json"
LOG_DIR    = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────
today_str = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"outreach_{today_str}.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("agent")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "first_run_date": today_str,
        "days_running": 0,
        "total_reddit_dms": 3,       # 3 already sent
        "total_reddit_comments": 0,
        "total_x_replies": 0,
        "seen_ids": ["1skn3n1", "1skl4ao", "1skq2bo", "1skoz7x", "1skpwak"],
        "sent_to": ["Sarahbeth822", "doobylive", "Scumpop"],
        "x_seen_ids": [],
        "today_dms": 0,
        "today_comments": 0,
        "today_x_replies": 0,
        "last_run": None,
        "last_report_date": None,
        "account_health": {"reddit": "active", "x": "no_session"},
    }


def save_state(state: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_queue() -> list:
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return []


def save_queue(q: list):
    QUEUE_FILE.parent.mkdir(exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(q[-1000:], indent=2))


def _today() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d")


def daily_limits(days_running: int) -> dict:
    """Conservative ramp — preserve account, maximize utilization."""
    if days_running <= 3:
        return {"reddit_dms": 5, "reddit_comments": 5, "x_replies": 8}
    elif days_running <= 7:
        return {"reddit_dms": 10, "reddit_comments": 8, "x_replies": 15}
    elif days_running <= 14:
        return {"reddit_dms": 15, "reddit_comments": 12, "x_replies": 20}
    else:
        return {"reddit_dms": 20, "reddit_comments": 15, "x_replies": 25}


def reset_daily_counts_if_new_day(state: dict) -> dict:
    """Reset today's counts at midnight CDT."""
    if state.get("last_count_reset") != _today():
        state["today_dms"] = 0
        state["today_comments"] = 0
        state["today_x_replies"] = 0
        state["last_count_reset"] = _today()
        # Increment days running
        state["days_running"] = state.get("days_running", 0) + 1
        log.info(f"Day {state['days_running']} — daily counts reset")
    return state


def run_cycle(dry_run: bool = False):
    """Execute one full 2-hour outreach cycle."""
    from ollama_client import available as ollama_available, draft_dm, draft_comment, draft_x_reply, draft_conversation_reply
    from abcd import sample_variant, record_send, record_reply, get_status, format_report
    from reddit_client import scan_subreddits, send_dm, post_comment, check_inbox
    from x_client import scan_x, reply_to_tweet
    from reporter import send_cycle_report

    log.info(f"{'='*50}")
    log.info(f"Cycle start | Ollama: {ollama_available()} | dry_run: {dry_run}")

    state = load_state()
    state = reset_daily_counts_if_new_day(state)
    limits = daily_limits(state.get("days_running", 0))

    log.info(f"Day {state['days_running']} limits: {limits}")
    log.info(f"Today so far: DMs={state['today_dms']}, comments={state['today_comments']}, X={state['today_x_replies']}")

    seen_ids = set(state.get("seen_ids", []))
    x_seen_ids = set(state.get("x_seen_ids", []))
    sent_to = set(state.get("sent_to", []))

    cycle_sent = []
    inbox_replies = []

    # ── 1. Check inbox for replies ─────────────────────────────────
    log.info("Checking Reddit inbox...")
    if not dry_run:
        try:
            new_replies = check_inbox()
            for reply in new_replies:
                author = reply.get("author", "")
                if not author: continue
                log.info(f"Reply from u/{author}: {reply['body'][:60]}")
                # Draft suggested response via Ollama
                suggested = draft_conversation_reply([], reply["body"]) if ollama_available() else ""
                reply["suggested_reply"] = suggested
                inbox_replies.append(reply)
        except Exception as e:
            log.warning(f"Inbox check error: {e}")

    # ── 2. Scan Reddit ─────────────────────────────────────────────
    log.info("Scanning Reddit...")
    reddit_posts = []
    try:
        reddit_posts = scan_subreddits(seen_ids)
    except Exception as e:
        log.error(f"Reddit scan failed: {e}")

    # ── 3. Scan X ──────────────────────────────────────────────────
    log.info("Scanning X...")
    x_posts = []
    try:
        x_posts = scan_x(x_seen_ids)
    except Exception as e:
        log.warning(f"X scan failed: {e}")

    # ── 4. Process Reddit posts ────────────────────────────────────
    for post in reddit_posts:
        seen_ids.add(post["id"])

        # Check limits
        can_dm      = state["today_dms"] < limits["reddit_dms"] and post["author"] not in sent_to
        can_comment = state["today_comments"] < limits["reddit_comments"] and post.get("comment_ok")

        if not can_dm and not can_comment:
            log.info(f"  Skipping r/{post['subreddit']} post — limits reached")
            continue

        # Pick ABCD variant via Thompson Sampling
        variant = sample_variant("dm") if can_dm else sample_variant("comment")

        # Draft via Ollama (or template fallback)
        dm_text = comment_text = ""
        if can_dm:
            dm_text = draft_dm(
                post["title"], post["author"], post["subreddit"],
                post.get("dfw", False), variant
            )
            if not dm_text:
                # Template fallback
                geo = "in DFW" if post.get("dfw") else "across DFW metro"
                dm_text = (
                    f"Saw your post about {post['title'][:50]}. "
                    f"I'm a licensed appraiser {geo} and this is directly relevant to what I do. "
                    f"Happy to give you a straight answer on the specifics. "
                    f"Luke Motto, Licensed DFW Appraiser, (817) 217-4375"
                )

        if can_comment:
            comment_text = draft_comment(
                post["title"], post.get("body", ""), post["subreddit"],
                post.get("intent", []), post.get("dfw", False), variant
            )

        log.info(f"Processing: r/{post['subreddit']} by u/{post['author']} | variant {variant}")
        if dm_text: log.info(f"  DM: {dm_text[:80]}...")
        if comment_text: log.info(f"  Comment: {comment_text[:80]}...")

        dm_sent = comment_sent = False

        if not dry_run:
            # Comment first (if eligible)
            if can_comment and comment_text:
                comment_sent = post_comment(post["url"], comment_text)
                if comment_sent:
                    state["today_comments"] += 1
                    state["total_reddit_comments"] = state.get("total_reddit_comments", 0) + 1
                time.sleep(random.uniform(20, 45))

            # Then DM
            if can_dm and dm_text:
                dm_sent = send_dm(post["author"], dm_text)
                if dm_sent:
                    state["today_dms"] += 1
                    state["total_reddit_dms"] = state.get("total_reddit_dms", 0) + 1
                    sent_to.add(post["author"])
                    record_send(variant, "dm")
                time.sleep(random.uniform(60, 90))

        cycle_sent.append({
            "type": "reddit_dm" if dm_sent else "reddit_comment" if comment_sent else "reddit_queued",
            "author": post["author"],
            "subreddit": post["subreddit"],
            "title": post["title"],
            "url": post["url"],
            "variant": variant,
            "dm_sent": dm_sent,
            "comment_sent": comment_sent,
            "dm_preview": dm_text[:120] if dm_text else "",
        })

    # ── 5. Process X posts ─────────────────────────────────────────
    for tweet in x_posts:
        x_seen_ids.add(tweet["id"])

        if state["today_x_replies"] >= limits["x_replies"]:
            break

        reply_text = draft_x_reply(
            tweet["text"], tweet["username"],
            [], False  # X: no intent/geo tagging yet
        )
        if not reply_text:
            reply_text = f"Licensed DFW appraiser here — happy to help with this. (817) 217-4375"
            reply_text = reply_text[:240]

        log.info(f"X reply to @{tweet['username']}: {reply_text[:60]}...")

        x_sent = False
        if not dry_run:
            x_sent = reply_to_tweet(tweet["url"], reply_text)
            if x_sent:
                state["today_x_replies"] += 1
                state["total_x_replies"] = state.get("total_x_replies", 0) + 1
            time.sleep(random.uniform(30, 60))

        cycle_sent.append({
            "type": "x_reply",
            "username": tweet["username"],
            "tweet": tweet["text"][:80],
            "url": tweet["url"],
            "reply": reply_text,
            "sent": x_sent,
        })

    # ── 6. Update state ────────────────────────────────────────────
    state["seen_ids"] = list(seen_ids)[-2000:]  # Keep last 2000
    state["x_seen_ids"] = list(x_seen_ids)[-2000:]
    state["sent_to"] = list(sent_to)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    # ── 7. Build and send report ───────────────────────────────────
    abcd_status = get_status("dm")
    cycle_summary = {
        "sent": cycle_sent,
        "account_health": {
            "reddit_dms_today": state["today_dms"],
            "reddit_dm_limit": limits["reddit_dms"],
            "reddit_status": "active",
            "x_replies_today": state["today_x_replies"],
            "x_limit": limits["x_replies"],
            "x_status": "active" if (BASE / "data" / "x_session.json").exists() else "no session",
        }
    }

    sent_count = sum(1 for s in cycle_sent if s.get("dm_sent") or s.get("comment_sent") or s.get("sent"))
    log.info(f"Cycle complete: {sent_count} sent | {len(inbox_replies)} replies received")

    if not dry_run and (cycle_sent or inbox_replies):
        send_cycle_report(cycle_summary, abcd_status, inbox_replies)

    # ── 8. Log to JSONL for sharpener ─────────────────────────────
    log_file = LOG_DIR / f"sends_{today_str}.jsonl"
    with open(log_file, "a") as f:
        for s in cycle_sent:
            f.write(json.dumps({**s, "timestamp": time.time()}) + "\n")

    return cycle_sent


# ── Sharpener (called separately once/day) ───────────────────────────

def run_sharpener():
    """Daily loop: analyze last 24h of sends, propose improvements."""
    from ollama_client import sharpen
    from abcd import get_status

    log.info("Running daily sharpener...")

    # Load recent sends from JSONL logs
    recent = []
    for log_file in sorted(LOG_DIR.glob("sends_*.jsonl"))[-2:]:
        with open(log_file) as f:
            for line in f:
                try:
                    recent.append(json.loads(line))
                except Exception:
                    pass

    if len(recent) < 3:
        log.info(f"Too few sends ({len(recent)}) for sharpener analysis")
        return

    analysis = sharpen(recent)
    if analysis:
        sharpener_log = BASE / "data" / "sharpener_log.jsonl"
        with open(sharpener_log, "a") as f:
            f.write(json.dumps(analysis) + "\n")
        log.info(f"Sharpener analysis written")
        if analysis.get("analysis"):
            log.info(f"  {analysis['analysis'][:200]}...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle",    action="store_true", help="Run one outreach cycle")
    parser.add_argument("--sharpen",  action="store_true", help="Run daily sharpener analysis")
    parser.add_argument("--dry-run",  action="store_true", help="Scan but don't send")
    parser.add_argument("--status",   action="store_true", help="Print current state and ABCD status")
    args = parser.parse_args()

    if args.status:
        from abcd import format_report
        state = load_state()
        print(json.dumps(state, indent=2))
        print("\n" + format_report("dm"))
    elif args.sharpen:
        run_sharpener()
    elif args.cycle or args.dry_run:
        run_cycle(dry_run=args.dry_run)
    else:
        parser.print_help()
