"""
queue.py — Content Queue Manager
Motto Appraisal Service | Content Distribution Pipeline

Local JSON-based queue for tracking content ready to post, pending review,
and already posted. No external database dependency.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUEUE_PATH = Path("/home/user/workspace/cron_tracking/distribution_queue.json")

# Queue item status values
STATUS_PENDING = "pending"
STATUS_REVIEW = "review_required"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# Valid platform identifiers
VALID_PLATFORMS = {
    "linkedin",
    "linkedin_group",
    "facebook_group",
    "x_post",
    "x_thread",
    "reddit",
    "medium",
    "substack",
    "beehiiv",
    "linkedin_article",
    "outreach",
    "sms",
    "pinterest",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_queue() -> dict:
    """Load the queue from disk. Creates an empty queue if file doesn't exist."""
    if not QUEUE_PATH.exists():
        return {"items": [], "meta": {"created_at": _now(), "version": "1.0"}}
    with QUEUE_PATH.open() as f:
        return json.load(f)


def _save_queue(queue: dict) -> None:
    """Persist the queue to disk."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    queue["meta"]["updated_at"] = _now()
    with QUEUE_PATH.open("w") as f:
        json.dump(queue, f, indent=2)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _generate_id() -> str:
    return str(uuid.uuid4())[:12]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_to_queue(
    post_urn: str,
    platform: str,
    content: str,
    requires_review: bool = False,
    metadata: Optional[dict] = None,
) -> str:
    """
    Add content to the posting queue.

    Args:
        post_urn: Source post identifier (e.g. "urn:li:activity:12345")
        platform: Target platform (see VALID_PLATFORMS)
        content: The content string to be posted (may be JSON-serialized for complex payloads)
        requires_review: If True, item goes to review queue instead of pending
        metadata: Optional extra context (pillar, format_type, char_count, etc.)

    Returns:
        item_id: Unique identifier for this queue item.

    Raises:
        ValueError: If platform is not recognized.
    """
    if platform not in VALID_PLATFORMS:
        raise ValueError(
            f"Unknown platform '{platform}'. Valid platforms: {sorted(VALID_PLATFORMS)}"
        )

    item_id = _generate_id()
    status = STATUS_REVIEW if requires_review else STATUS_PENDING

    item = {
        "item_id": item_id,
        "post_urn": post_urn,
        "platform": platform,
        "content": content,
        "status": status,
        "requires_review": requires_review,
        "created_at": _now(),
        "updated_at": _now(),
        "posted_at": None,
        "result": None,
        "metadata": metadata or {},
    }

    queue = _load_queue()
    queue["items"].append(item)
    _save_queue(queue)

    return item_id


def get_pending(platform: Optional[str] = None) -> list[dict]:
    """
    Get pending queue items, optionally filtered by platform.

    Args:
        platform: If provided, only return items for this platform.

    Returns:
        List of pending queue item dicts.
    """
    queue = _load_queue()
    items = [i for i in queue["items"] if i["status"] == STATUS_PENDING]

    if platform:
        items = [i for i in items if i["platform"] == platform]

    return items


def mark_posted(item_id: str, result: dict) -> None:
    """
    Mark a queue item as posted with the API result.

    Args:
        item_id: The item ID returned by add_to_queue.
        result: The result dict from the posting API (e.g. tweet result, beehiiv post result).
    """
    queue = _load_queue()
    for item in queue["items"]:
        if item["item_id"] == item_id:
            item["status"] = STATUS_POSTED
            item["posted_at"] = _now()
            item["updated_at"] = _now()
            item["result"] = result
            break
    else:
        raise KeyError(f"Queue item '{item_id}' not found.")
    _save_queue(queue)


def mark_failed(item_id: str, error: str) -> None:
    """
    Mark a queue item as failed.

    Args:
        item_id: The item ID.
        error: Error message or traceback.
    """
    queue = _load_queue()
    for item in queue["items"]:
        if item["item_id"] == item_id:
            item["status"] = STATUS_FAILED
            item["updated_at"] = _now()
            item["result"] = {"error": error}
            break
    else:
        raise KeyError(f"Queue item '{item_id}' not found.")
    _save_queue(queue)


def mark_skipped(item_id: str, reason: str) -> None:
    """
    Mark a queue item as skipped (e.g., auto-post disabled).

    Args:
        item_id: The item ID.
        reason: Why the item was skipped.
    """
    queue = _load_queue()
    for item in queue["items"]:
        if item["item_id"] == item_id:
            item["status"] = STATUS_SKIPPED
            item["updated_at"] = _now()
            item["result"] = {"skipped_reason": reason}
            break
    else:
        raise KeyError(f"Queue item '{item_id}' not found.")
    _save_queue(queue)


def get_review_queue() -> list[dict]:
    """
    Get all items flagged for manual review.

    Returns:
        List of queue items with status "review_required".
    """
    queue = _load_queue()
    return [i for i in queue["items"] if i["status"] == STATUS_REVIEW]


def get_all(status: Optional[str] = None) -> list[dict]:
    """
    Get all queue items, optionally filtered by status.

    Args:
        status: "pending" | "review_required" | "posted" | "failed" | "skipped" | None (all)

    Returns:
        List of queue item dicts.
    """
    queue = _load_queue()
    items = queue["items"]
    if status:
        items = [i for i in items if i["status"] == status]
    return items


def get_item(item_id: str) -> dict:
    """
    Get a single queue item by ID.

    Args:
        item_id: The item ID.

    Returns:
        Queue item dict.

    Raises:
        KeyError: If item not found.
    """
    queue = _load_queue()
    for item in queue["items"]:
        if item["item_id"] == item_id:
            return item
    raise KeyError(f"Queue item '{item_id}' not found.")


def get_stats() -> dict:
    """
    Get queue statistics summary.

    Returns:
        Dict with counts per status and total.
    """
    queue = _load_queue()
    items = queue["items"]

    stats: dict[str, int] = {
        STATUS_PENDING: 0,
        STATUS_REVIEW: 0,
        STATUS_POSTED: 0,
        STATUS_FAILED: 0,
        STATUS_SKIPPED: 0,
        "total": len(items),
    }

    for item in items:
        s = item.get("status", STATUS_PENDING)
        if s in stats:
            stats[s] += 1

    # Platform breakdown
    platform_counts: dict[str, int] = {}
    for item in items:
        p = item.get("platform", "unknown")
        platform_counts[p] = platform_counts.get(p, 0) + 1

    return {
        "status_counts": stats,
        "platform_counts": platform_counts,
        "queue_path": str(QUEUE_PATH),
        "last_updated": queue.get("meta", {}).get("updated_at", "unknown"),
    }


def clear_posted(older_than_days: int = 30) -> int:
    """
    Remove posted items older than N days to keep the queue file manageable.

    Args:
        older_than_days: Remove posted items older than this many days.

    Returns:
        Number of items removed.
    """
    import datetime

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=older_than_days)
    queue = _load_queue()
    original_count = len(queue["items"])

    def _should_keep(item: dict) -> bool:
        if item["status"] != STATUS_POSTED:
            return True
        posted_at = item.get("posted_at")
        if not posted_at:
            return True
        try:
            posted_dt = datetime.datetime.strptime(posted_at, "%Y-%m-%dT%H:%M:%SZ")
            return posted_dt > cutoff
        except ValueError:
            return True

    queue["items"] = [i for i in queue["items"] if _should_keep(i)]
    removed = original_count - len(queue["items"])
    if removed > 0:
        _save_queue(queue)
    return removed


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Content queue manager for Motto Appraisal")
    parser.add_argument("--stats", action="store_true", help="Show queue statistics")
    parser.add_argument("--pending", action="store_true", help="List pending items")
    parser.add_argument("--review", action="store_true", help="List items needing review")
    parser.add_argument("--platform", type=str, help="Filter by platform")
    parser.add_argument(
        "--clear-old", type=int, metavar="DAYS", help="Remove posted items older than N days"
    )
    args = parser.parse_args()

    if args.stats:
        stats = get_stats()
        print(json.dumps(stats, indent=2))

    elif args.pending:
        items = get_pending(platform=args.platform)
        print(f"Pending items ({len(items)}):")
        for item in items:
            print(
                f"  [{item['item_id']}] {item['platform']} | "
                f"Source: {item['post_urn']} | Created: {item['created_at']}"
            )

    elif args.review:
        items = get_review_queue()
        print(f"Review queue ({len(items)} items):")
        for item in items:
            print(
                f"  [{item['item_id']}] {item['platform']} | "
                f"Source: {item['post_urn']} | Created: {item['created_at']}"
            )

    elif args.clear_old is not None:
        removed = clear_posted(older_than_days=args.clear_old)
        print(f"Removed {removed} old posted items from queue.")

    else:
        parser.print_help()
