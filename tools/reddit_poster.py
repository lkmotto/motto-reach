"""
reddit_poster.py — Reddit content distribution tool

Strategy:
- Primary: PRAW-based posting when Reddit API credentials are available
- Fallback: Add to manual review queue with formatted post ready to copy-paste
- NEVER auto-post to subreddits without manual review — promotion risk is too high
- All posts are flagged as manual_review_required=True

Reddit credentialing note:
  Reddit requires OAuth app credentials from reddit.com/prefs/apps
  Script type app: client_id + client_secret + username + password
  Stored at /home/user/workspace/credentials/reddit_credentials.json (may not exist yet)

Approved subreddits for Motto Appraisal content:
  r/realestateinvesting — 1.2M members, DFW investors, DSCR/deal math content works
  r/RealEstate — 1.2M members, homeowner/buyer education
  r/FirstTimeHomeBuyer — appraisal education, property tax
  r/appraisal — professional community, appraiser's lens content
  r/personalfinance — property tax, financing content
  r/legaladvice — estate/divorce appraisal content (when relevant)
  r/realestate_dfw — local community (check if exists)
  r/Texas — TX market intel content
  r/dfw — local market data
"""

import os
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

CREDENTIALS_PATH = Path("/home/user/workspace/credentials/reddit_credentials.json")
QUEUE_PATH = Path("/home/user/workspace/cron_tracking/reddit_review_queue.json")

SUBREDDIT_RULES = {
    "r/realestateinvesting": {
        "allowed_pillars": [1, 2, 3, 4],
        "tone": "educational_investor",
        "promotion_risk": "medium",
        "notes": "Must add value. No soft CTAs. Appraiser credibility is an asset here.",
    },
    "r/RealEstate": {
        "allowed_pillars": [1, 3, 6],
        "tone": "educational_homeowner",
        "promotion_risk": "low",
        "notes": "Homeowner-focused. Property tax, AVM accuracy, appraisal process.",
    },
    "r/FirstTimeHomeBuyer": {
        "allowed_pillars": [1, 6],
        "tone": "helpful_educational",
        "promotion_risk": "low",
        "notes": "Never promotional. Pure education. Comments on existing threads are best.",
    },
    "r/appraisal": {
        "allowed_pillars": [1, 5],
        "tone": "professional_practitioner",
        "promotion_risk": "low",
        "notes": "Professional community. Share appraiser perspective authentically.",
    },
    "r/personalfinance": {
        "allowed_pillars": [6],
        "tone": "educational_neutral",
        "promotion_risk": "high",
        "notes": "Strict no-marketing rules. Only pure education about property tax, appraisal process.",
    },
    "r/Texas": {
        "allowed_pillars": [3, 6],
        "tone": "local_informative",
        "promotion_risk": "medium",
        "notes": "TX market data, property tax breakdowns. Mention DFW context.",
    },
    "r/dfw": {
        "allowed_pillars": [3, 6],
        "tone": "local_community",
        "promotion_risk": "medium",
        "notes": "Local DFW community. Market data and property tax are relevant.",
    },
}


def _load_queue() -> list:
    """Load existing queue or return empty list."""
    try:
        if QUEUE_PATH.exists():
            return json.loads(QUEUE_PATH.read_text())
        return []
    except Exception as e:
        log.warning(f"Could not load Reddit queue: {e}")
        return []


def _save_queue(queue: list) -> None:
    """Persist queue to disk, creating parent directories as needed."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def _build_posting_instructions(subreddit: str, title: str, body: str, flair: Optional[str]) -> str:
    """Build a copy-paste ready posting instruction block."""
    clean_sub = subreddit.lstrip("r/")
    flair_line = f"\n7. Flair: {flair}" if flair else "\n7. Flair: (none)"
    return (
        "REDDIT POSTING INSTRUCTIONS\n"
        "============================\n"
        f"1. Log in as /u/Opposite_Ground594\n"
        f"2. Go to https://reddit.com/r/{clean_sub}/submit\n"
        "3. Select: Text post\n"
        f"4. Title: {title}\n"
        f"5. Body:\n\n{body}\n"
        f"6. Read the sidebar rules before posting{flair_line}\n"
        "8. Post and monitor for 30min — respond to any comments"
    )


def add_to_review_queue(
    subreddit: str,
    title: str,
    body: str,
    source_post_urn: str,
    pillar: int,
    flair: Optional[str] = None,
) -> str:
    """
    Add a post to the manual review queue.
    Returns queue item ID.

    Queue item format:
    {
        "id": str,
        "created_at": ISO8601,
        "status": "pending_review",
        "subreddit": str,
        "title": str,
        "body": str,
        "source_post_urn": str,
        "pillar": int,
        "flair": str | None,
        "review_notes": str,
        "promotion_risk": str,
        "posting_instructions": str  // step-by-step for manual posting
    }
    """
    try:
        rules = SUBREDDIT_RULES.get(subreddit, {})
        promotion_risk = rules.get("promotion_risk", "unknown")
        review_notes = rules.get("notes", "Review subreddit rules before posting.")

        item_id = str(uuid.uuid4())
        item = {
            "id": item_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_review",
            "manual_review_required": True,
            "subreddit": subreddit,
            "title": title,
            "body": body,
            "source_post_urn": source_post_urn,
            "pillar": pillar,
            "flair": flair,
            "review_notes": review_notes,
            "promotion_risk": promotion_risk,
            "posting_instructions": _build_posting_instructions(subreddit, title, body, flair),
        }

        queue = _load_queue()
        queue.append(item)
        _save_queue(queue)
        log.info(f"Added Reddit review item {item_id} for {subreddit}")
        return item_id

    except Exception as e:
        log.error(f"Failed to add Reddit review item: {e}")
        return ""


def post_to_subreddit(
    subreddit: str,
    title: str,
    body: str,
    flair: Optional[str] = None,
    source_post_urn: str = "",
    pillar: int = 1,
) -> dict:
    """
    Attempt to post to a subreddit using PRAW.
    Falls back to manual review queue if credentials unavailable or posting fails.

    ALWAYS returns the queue item ID — post may be auto-posted or queued for review.
    Note: manual_review_required is always True per policy.
    """
    # Policy: always queue for manual review, never auto-post
    item_id = add_to_review_queue(
        subreddit=subreddit,
        title=title,
        body=body,
        source_post_urn=source_post_urn,
        pillar=pillar,
        flair=flair,
    )

    praw_client = _get_praw_client()
    if praw_client is not None:
        log.info(
            f"PRAW client available but manual_review_required=True — "
            f"queued item {item_id} instead of auto-posting to {subreddit}"
        )

    return {
        "queue_item_id": item_id,
        "subreddit": subreddit,
        "manual_review_required": True,
        "status": "pending_review",
    }


def queue_for_subreddits(
    post_text: str,
    title: str,
    source_post_urn: str,
    pillar: int,
    reddit_version: Optional[dict] = None,
) -> list[str]:
    """
    Queue a post for all subreddits appropriate for the given pillar.
    If reddit_version dict is provided, use its title/body fields.
    Returns list of queue item IDs.
    """
    item_ids: list[str] = []
    try:
        suitable = get_subreddit_recommendations(pillar)

        if reddit_version and isinstance(reddit_version, dict):
            post_title = reddit_version.get("title", title)
            post_body = reddit_version.get("body", post_text)
            flair = reddit_version.get("flair")
        else:
            post_title = title
            post_body = post_text
            flair = None

        for subreddit in suitable:
            item_id = add_to_review_queue(
                subreddit=subreddit,
                title=post_title,
                body=post_body,
                source_post_urn=source_post_urn,
                pillar=pillar,
                flair=flair,
            )
            if item_id:
                item_ids.append(item_id)

    except Exception as e:
        log.error(f"queue_for_subreddits failed: {e}")

    return item_ids


def get_pending_review() -> list[dict]:
    """Get all items pending manual review."""
    try:
        queue = _load_queue()
        return [item for item in queue if item.get("status") == "pending_review"]
    except Exception as e:
        log.error(f"get_pending_review failed: {e}")
        return []


def get_subreddit_recommendations(pillar: int) -> list[str]:
    """Return suitable subreddits for a given content pillar."""
    recommended = []
    for subreddit, rules in SUBREDDIT_RULES.items():
        if pillar in rules.get("allowed_pillars", []):
            recommended.append(subreddit)
    return recommended


def mark_posted(item_id: str, reddit_url: str) -> bool:
    """Mark a queue item as posted with the live URL."""
    try:
        queue = _load_queue()
        for item in queue:
            if item["id"] == item_id:
                item["status"] = "posted"
                item["posted_at"] = datetime.now(timezone.utc).isoformat()
                item["reddit_url"] = reddit_url
                _save_queue(queue)
                return True
        log.warning(f"Item {item_id} not found in Reddit queue")
        return False
    except Exception as e:
        log.error(f"mark_posted failed: {e}")
        return False


def mark_skipped(item_id: str, reason: str) -> bool:
    """Mark a queue item as skipped."""
    try:
        queue = _load_queue()
        for item in queue:
            if item["id"] == item_id:
                item["status"] = "skipped"
                item["skip_reason"] = reason
                item["skipped_at"] = datetime.now(timezone.utc).isoformat()
                _save_queue(queue)
                return True
        return False
    except Exception as e:
        log.error(f"mark_skipped failed: {e}")
        return False


def _get_praw_client():
    """Return authenticated PRAW client or None if credentials unavailable."""
    try:
        import praw  # type: ignore
        creds = json.loads(CREDENTIALS_PATH.read_text())
        return praw.Reddit(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            username=creds["username"],
            password=creds["password"],
            user_agent="MottoappraisalBot/1.0 (by /u/Opposite_Ground594)",
        )
    except Exception as e:
        log.warning(f"PRAW client unavailable: {e}")
        return None
