"""
facebook_groups.py — Facebook group content distribution

Two modes:
1. Groups the page manages (POST /group_id/feed with page token)
2. Groups Luke is a member of personally (manual review queue — use personal token)

Strategy:
- Auto-post only to groups the page manages (if any)
- Queue everything else for manual review
- Generate native Facebook community voice (discussion-led, less formal than LinkedIn)
"""

import json
import logging
import uuid
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

FB_TOKEN_PATH = Path("/home/user/workspace/linkedin_poster/fb_page_token.txt")
QUEUE_PATH = Path("/home/user/workspace/cron_tracking/facebook_groups_queue.json")
GRAPH_API = "https://graph.facebook.com/v21.0"

# Relevant Facebook groups for appraisal/real estate content
# These are the types to join and engage in
RELEVANT_GROUP_TYPES = [
    "DFW Real Estate Investors",
    "Texas Real Estate Network",
    "DFW Homebuyers & Sellers",
    "Fort Worth Real Estate",
    "Dallas Real Estate Professionals",
    "Texas Property Tax Help",
    "DSCR & Investment Property Loans",
]

# Confirmed managed groups: populate with actual group IDs once known.
# Format: [{"id": "group_id", "name": "Group Name"}]
MANAGED_GROUPS: list[dict] = []


def _get_token() -> str:
    """Read the Facebook page token from disk."""
    try:
        return FB_TOKEN_PATH.read_text().strip()
    except Exception as e:
        log.error(f"Could not read Facebook page token: {e}")
        return ""


def _load_queue() -> list:
    """Load existing queue or return empty list."""
    try:
        if QUEUE_PATH.exists():
            return json.loads(QUEUE_PATH.read_text())
        return []
    except Exception as e:
        log.warning(f"Could not load Facebook groups queue: {e}")
        return []


def _save_queue(queue: list) -> None:
    """Persist queue to disk, creating parent directories as needed."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def _build_posting_instructions(
    group_name: str, group_url: str, post_text: str, image_path: Optional[str] = None
) -> str:
    """Build a copy-paste ready posting instruction block for a Facebook group."""
    image_line = f"\n6. Attach image: {image_path}" if image_path else ""
    return (
        "FACEBOOK GROUP POSTING INSTRUCTIONS\n"
        "=====================================\n"
        f"Group: {group_name}\n"
        f"URL: {group_url}\n\n"
        "Steps:\n"
        "1. Go to the group URL above\n"
        "2. Click 'Write something...' in the post composer\n"
        "3. Paste the following content:\n\n"
        "--- POST CONTENT ---\n"
        f"{post_text}\n"
        f"--- END CONTENT ---{image_line}\n\n"
        "REVIEW CHECKLIST:\n"
        "[ ] Have you read the group rules?\n"
        "[ ] Is this educational and community-focused (not an ad)?\n"
        "[ ] Is there no pricing, booking link, or direct CTA?\n"
        "[ ] Does the post invite discussion or ask a question?\n"
        "[ ] Have you posted in this group in the last 3 days? (Avoid spam flags)\n"
    )


def post_to_managed_group(
    group_id: str, message: str, image_url: Optional[str] = None
) -> dict:
    """
    Post to a Facebook group the page manages.
    Uses page token. Returns post ID or error.
    """
    token = _get_token()
    if not token:
        return {"success": False, "error": "Facebook page token unavailable"}

    try:
        payload: dict = {
            "message": message,
            "access_token": token,
        }
        if image_url:
            payload["link"] = image_url

        resp = requests.post(
            f"{GRAPH_API}/{group_id}/feed",
            data=payload,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            post_id = data.get("id", "")
            log.info(f"Posted to managed Facebook group {group_id}: {post_id}")
            return {
                "success": True,
                "post_id": post_id,
                "group_id": group_id,
                "url": f"https://www.facebook.com/groups/{group_id}/",
            }
        else:
            error_msg = resp.text[:300]
            log.error(f"Facebook group post failed ({resp.status_code}): {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": resp.status_code,
                "group_id": group_id,
            }

    except Exception as e:
        log.error(f"post_to_managed_group exception: {e}")
        return {"success": False, "error": str(e), "group_id": group_id}


def queue_for_manual_review(
    group_name: str,
    group_url: str,
    post_text: str,
    source_post_urn: str,
    pillar: int,
    image_path: Optional[str] = None,
) -> str:
    """
    Add Facebook group post to manual review queue.
    Includes posting instructions for the human.
    Returns queue item ID.
    """
    try:
        item_id = str(uuid.uuid4())
        item = {
            "id": item_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_review",
            "manual_review_required": True,
            "group_name": group_name,
            "group_url": group_url,
            "post_text": post_text,
            "source_post_urn": source_post_urn,
            "pillar": pillar,
            "image_path": image_path,
            "posting_instructions": _build_posting_instructions(
                group_name, group_url, post_text, image_path
            ),
        }

        queue = _load_queue()
        queue.append(item)
        _save_queue(queue)

        log.info(f"Queued Facebook group item {item_id} for '{group_name}'")
        return item_id

    except Exception as e:
        log.error(f"queue_for_manual_review failed: {e}")
        return ""


def queue_for_relevant_groups(
    post_text: str,
    source_post_urn: str,
    pillar: int,
    fb_version: Optional[dict] = None,
    image_path: Optional[str] = None,
) -> list[str]:
    """
    Queue Facebook group posts for all relevant group types.
    Uses fb_version dict if available for native-voice text.
    Returns list of queue item IDs.
    """
    item_ids: list[str] = []
    try:
        final_text = post_text
        if fb_version and isinstance(fb_version, dict):
            final_text = fb_version.get("body", post_text)

        for group_name in RELEVANT_GROUP_TYPES:
            # Build a search URL to help the human find the group
            encoded_name = group_name.replace(" ", "%20")
            group_url = f"https://www.facebook.com/search/groups/?q={encoded_name}"

            item_id = queue_for_manual_review(
                group_name=group_name,
                group_url=group_url,
                post_text=final_text,
                source_post_urn=source_post_urn,
                pillar=pillar,
                image_path=image_path,
            )
            if item_id:
                item_ids.append(item_id)

    except Exception as e:
        log.error(f"queue_for_relevant_groups failed: {e}")

    return item_ids


def get_managed_groups() -> list[dict]:
    """
    Fetch Facebook groups the page manages via Graph API.
    Falls back to MANAGED_GROUPS constant if API call fails.
    """
    token = _get_token()
    if not token:
        log.warning("No Facebook token — returning configured MANAGED_GROUPS list")
        return MANAGED_GROUPS

    try:
        resp = requests.get(
            f"{GRAPH_API}/me/groups",
            params={
                "access_token": token,
                "fields": "id,name,privacy,member_count",
            },
            timeout=30,
        )

        if resp.status_code == 200:
            data = resp.json()
            groups = data.get("data", [])
            log.info(f"Fetched {len(groups)} managed Facebook groups")
            return groups
        else:
            log.warning(
                f"Could not fetch managed groups ({resp.status_code}): {resp.text[:200]}"
            )
            return MANAGED_GROUPS

    except Exception as e:
        log.error(f"get_managed_groups failed: {e}")
        return MANAGED_GROUPS


def get_pending_review() -> list[dict]:
    """Get all pending Facebook group posts."""
    try:
        queue = _load_queue()
        return [item for item in queue if item.get("status") == "pending_review"]
    except Exception as e:
        log.error(f"get_pending_review failed: {e}")
        return []


def mark_posted(item_id: str, fb_post_url: str = "") -> bool:
    """Mark a queue item as posted."""
    try:
        queue = _load_queue()
        for item in queue:
            if item["id"] == item_id:
                item["status"] = "posted"
                item["posted_at"] = datetime.now(timezone.utc).isoformat()
                if fb_post_url:
                    item["fb_post_url"] = fb_post_url
                _save_queue(queue)
                return True
        log.warning(f"Item {item_id} not found in Facebook groups queue")
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
