"""
reporter.py — Email digest sender
Sends a plain-text summary after each cycle where something was sent.
Uses smtplib with Gmail App Password (env: GMAIL_APP_PASSWORD).
Falls back to writing a pending_report.json for the Perplexity connector to send.
"""
import os, json, smtplib, logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime, timezone, timedelta

log = logging.getLogger("reporter")

GMAIL_FROM    = "ljm32901@gmail.com"
GMAIL_TO      = "ljm32901@gmail.com"
GMAIL_APP_PWD = os.getenv("GMAIL_APP_PASSWORD", "")
PENDING_FILE  = Path(__file__).parent / "data" / "pending_report.json"


def _cdt_now() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%B %d, %Y %I:%M %p CDT")


def build_email_body(cycle_summary: dict, abcd_status: dict, inbox_replies: list, sharpener_note: str = "") -> str:
    sent = cycle_summary.get("sent", [])
    reddit_dms = sum(1 for s in sent if s.get("type") == "reddit_dm")
    reddit_comments = sum(1 for s in sent if s.get("type") == "reddit_comment")
    x_replies = sum(1 for s in sent if s.get("type") == "x_reply")

    lines = [
        f"OUTREACH SUMMARY — {_cdt_now()}",
        "=" * 42,
        "",
        "SENT THIS CYCLE:",
        f"  Reddit DMs:      {reddit_dms}",
        f"  Reddit Comments: {reddit_comments}",
        f"  X Replies:       {x_replies}",
        "",
    ]

    if sent:
        lines.append("TOP TARGETS:")
        for i, s in enumerate(sent[:8], 1):
            platform = s.get("type","").replace("_"," ").title()
            target = f"u/{s.get('author','?')}" if "reddit" in s.get("type","") else f"@{s.get('username','?')}"
            lines.append(f"  {i}. {target} (r/{s.get('subreddit','?')} | Variant {s.get('variant','?')}) — {s.get('title','')[:55]}")
            lines.append(f"     DM: {'yes' if s.get('dm_sent') else 'no'} | Comment: {'yes' if s.get('comment_sent') else 'no'}")
        lines.append("")

    if inbox_replies:
        lines.append("REPLIES RECEIVED:")
        for r in inbox_replies[:5]:
            lines.append(f"  - u/{r.get('author','?')} replied:")
            lines.append(f"    \"{r.get('body','')[:120]}\"")
            suggested = r.get("suggested_reply", "")
            if suggested:
                lines.append(f"    Suggested response: {suggested[:150]}")
            lines.append("")
    else:
        lines.append("REPLIES RECEIVED: None this cycle")
        lines.append("")

    # ABCD status
    if abcd_status:
        lines.append("ABCD EXPERIMENT (Reddit DMs):")
        variants = abcd_status.get("variants", {})
        for v_id, v in variants.items():
            leader = " <-- LEADING" if v_id == abcd_status.get("leader") else ""
            lines.append(
                f"  Variant {v_id} ({v.get('name','?')}): "
                f"{v.get('sends',0)} sends | {v.get('reply_rate',0)}% reply rate | "
                f"P(best)={v.get('p_best',0)}%{leader}"
            )
        lines.append(f"  Days running: {abcd_status.get('days_running', 0)}")
        lines.append("")

    account = cycle_summary.get("account_health", {})
    lines.append("ACCOUNT HEALTH:")
    lines.append(f"  Reddit: {account.get('reddit_dms_today',0)} DMs today (limit: {account.get('reddit_dm_limit',0)}) | status: {account.get('reddit_status','active')}")
    lines.append(f"  X: {account.get('x_replies_today',0)} replies today (limit: {account.get('x_limit',0)}) | session: {account.get('x_status','no session')}")
    lines.append("")

    if sharpener_note:
        lines.append("SHARPENER NOTE:")
        lines.append(f"  {sharpener_note}")
        lines.append("")

    lines.append("─" * 42)
    lines.append("Reply to this email with a username + message to send a manual DM.")
    lines.append("mottoappraisal.cloud | (817) 217-4375")

    return "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    """Send via Gmail SMTP (App Password). Falls back to pending file."""
    if GMAIL_APP_PWD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = GMAIL_FROM
            msg["To"] = GMAIL_TO
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_FROM, GMAIL_APP_PWD)
                server.sendmail(GMAIL_FROM, [GMAIL_TO], msg.as_string())

            log.info(f"Email sent: {subject}")
            return True
        except Exception as e:
            log.error(f"SMTP failed: {e}")

    # Fallback: write to pending file for Perplexity connector
    PENDING_FILE.parent.mkdir(exist_ok=True)
    PENDING_FILE.write_text(json.dumps({"subject": subject, "body": body}))
    log.info(f"Email queued in pending_report.json (GMAIL_APP_PASSWORD not set)")
    return False


def send_cycle_report(cycle_summary: dict, abcd_status: dict,
                      inbox_replies: list, sharpener_note: str = "") -> bool:
    """Build and send the cycle digest email."""
    sent = cycle_summary.get("sent", [])
    if not sent and not inbox_replies:
        log.debug("Nothing to report this cycle")
        return False

    reddit_count = sum(1 for s in sent if "reddit" in s.get("type",""))
    x_count = sum(1 for s in sent if s.get("type") == "x_reply")

    subject = f"Outreach Report {_cdt_now()} — {reddit_count} Reddit + {x_count} X"
    body = build_email_body(cycle_summary, abcd_status, inbox_replies, sharpener_note)
    return send_email(subject, body)
