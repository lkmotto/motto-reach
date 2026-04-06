"""
linkedin_groups.py — LinkedIn group content distribution

LinkedIn API does not expose group posting endpoints.
This tool:
1. Generates group-safe content (less promotional, educational, discussion-first)
2. Identifies relevant LinkedIn groups for appraisal/real estate content
3. Adds to manual review queue with direct posting links
4. Tracks what's been posted to avoid repetition

Relevant LinkedIn groups (curated list — expand over time):
- Real Estate Investment & Development (large, DFW investors)
- Texas Real Estate Professionals
- DFW Real Estate Network
- DSCR Lending & Investment Property Finance
- Real Estate Appraisers Network
- Property Management & Real Estate Investors
- National Association of Mortgage Professionals
"""

import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

QUEUE_PATH = Path("/home/user/workspace/cron_tracking/linkedin_groups_queue.json")

# Curated group list with metadata
# Group IDs can be found in the URL: linkedin.com/groups/{id}/
RELEVANT_GROUPS = [
    {
        "name": "Real Estate Investment & Development",
        "search_url": "https://www.linkedin.com/search/results/groups/?keywords=real%20estate%20investment",
        "content_fit": [1, 2, 3, 4],
        "tone": "professional_investor",
        "promotion_risk": "medium",
        "notes": "Large active group. Lead with data and insight. No overt self-promotion.",
    },
    {
        "name": "Texas Real Estate Network",
        "search_url": "https://www.linkedin.com/search/results/groups/?keywords=texas%20real%20estate",
        "content_fit": [1, 2, 3, 4, 5, 6],
        "tone": "local_professional",
        "promotion_risk": "low",
        "notes": "Texas-specific. Mention DFW market context. All pillars work here.",
    },
    {
        "name": "DSCR & Investment Property Lending",
        "search_url": "https://www.linkedin.com/search/results/groups/?keywords=DSCR%20lending",
        "content_fit": [2, 4],
        "tone": "lender_focused",
        "promotion_risk": "medium",
        "notes": "Lender and broker audience. Focus on appraisal impact on loan viability.",
    },
    {
        "name": "Real Estate Appraisers Network",
        "search_url": "https://www.linkedin.com/search/results/groups/?keywords=real%20estate%20appraisers",
        "content_fit": [1, 5, 6],
        "tone": "professional_peer",
        "promotion_risk": "low",
        "notes": "Peer community. Practitioner perspective. Avoid marketing language entirely.",
    },
    {
        "name": "DFW Real Estate Network",
        "search_url": "https://www.linkedin.com/search/results/groups/?keywords=DFW%20real%20estate",
        "content_fit": [1, 2, 3, 4, 6],
        "tone": "local_professional",
        "promotion_risk": "low",
        "notes": "Local DFW focus. All educational content is welcome.",
    },
    {
        "name": "Property Management & Real Estate Investors",
        "search_url": "https://www.linkedin.com/search/results/groups/?keywords=property%20management%20real%20estate%20investors",
        "content_fit": [2, 3, 4],
        "tone": "investor_operator",
        "promotion_risk": "medium",
        "notes": "Investors and operators. Focus on value impact, condition adjustments, DSCR.",
    },
    {
        "name": "National Association of Mortgage Professionals",
        "search_url": "https://www.linkedin.com/search/results/groups/?keywords=mortgage%20professionals%20association",
        "content_fit": [1, 2, 4],
        "tone": "professional_lender",
        "promotion_risk": "medium",
        "notes": "Mortgage professional audience. Focus on appraisal process and risk.",
    },
]


def _load_queue() -> list:
    """Load existing queue or return empty list."""
    try:
        if QUEUE_PATH.exists():
            return json.loads(QUEUE_PATH.read_text())
        return []
    except Exception as e:
        log.warning(f"Could not load LinkedIn groups queue: {e}")
        return []


def _save_queue(queue: list) -> None:
    """Persist queue to disk, creating parent directories as needed."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def _build_posting_instructions(group: dict, post_text: str, discussion_question: Optional[str]) -> str:
    """Build a copy-paste ready posting instruction block for a LinkedIn group."""
    full_text = post_text
    if discussion_question:
        full_text = f"{post_text}\n\n{discussion_question}"

    review_checklist = (
        "MANUAL REVIEW CHECKLIST\n"
        "-----------------------\n"
        "[ ] Have you read the group rules/guidelines?\n"
        "[ ] Is this post educational (not promotional)?\n"
        "[ ] Does the post invite discussion rather than just broadcasting?\n"
        "[ ] Is there any mention of pricing, booking, or services? (Remove if yes)\n"
        "[ ] Have you posted in this group in the last 7 days? (Avoid over-posting)\n"
    )

    return (
        "LINKEDIN GROUP POSTING INSTRUCTIONS\n"
        "=====================================\n"
        f"Group: {group['name']}\n"
        f"Find the group: {group['search_url']}\n\n"
        "Steps:\n"
        "1. Search for the group using the link above\n"
        "2. Join the group if not already a member\n"
        "3. Click 'Create a post' inside the group\n"
        "4. Paste the following content:\n\n"
        "--- POST CONTENT ---\n"
        f"{full_text}\n"
        "--- END CONTENT ---\n\n"
        f"{review_checklist}\n"
        f"Tone guidance: {group.get('tone', 'professional')}\n"
        f"Notes: {group.get('notes', '')}"
    )


def queue_for_groups(
    post_text: str,
    group_safe_version: str,
    source_post_urn: str,
    pillar: int,
    discussion_question: Optional[str] = None,
) -> list[str]:
    """
    Add group-safe content to manual review queue for relevant groups.
    Returns list of queue item IDs.

    Each queue item includes:
    - The formatted group post text
    - Direct link to find and join the group
    - Posting instructions
    - Manual review checklist (have you read group rules? is this educational?)
    """
    item_ids: list[str] = []
    try:
        suitable_groups = get_group_recommendations(pillar)

        for group in suitable_groups:
            try:
                item_id = str(uuid.uuid4())

                # Build the final post text (append discussion question if provided)
                final_text = group_safe_version if group_safe_version else post_text
                if discussion_question:
                    final_text = f"{final_text}\n\n{discussion_question}"

                item = {
                    "id": item_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "status": "pending_review",
                    "manual_review_required": True,
                    "group_name": group["name"],
                    "group_search_url": group["search_url"],
                    "post_text": final_text,
                    "source_post_urn": source_post_urn,
                    "pillar": pillar,
                    "discussion_question": discussion_question,
                    "tone": group.get("tone", "professional"),
                    "promotion_risk": group.get("promotion_risk", "unknown"),
                    "content_fit": group.get("content_fit", []),
                    "posting_instructions": _build_posting_instructions(group, group_safe_version or post_text, discussion_question),
                }

                queue = _load_queue()
                queue.append(item)
                _save_queue(queue)

                log.info(f"Queued LinkedIn group item {item_id} for '{group['name']}'")
                item_ids.append(item_id)

            except Exception as e:
                log.error(f"Failed to queue LinkedIn group '{group['name']}': {e}")

    except Exception as e:
        log.error(f"queue_for_groups failed: {e}")

    return item_ids


def get_pending_review() -> list[dict]:
    """Get all pending LinkedIn group posts."""
    try:
        queue = _load_queue()
        return [item for item in queue if item.get("status") == "pending_review"]
    except Exception as e:
        log.error(f"get_pending_review failed: {e}")
        return []


def get_group_recommendations(pillar: int) -> list[dict]:
    """Return suitable groups for a given content pillar."""
    return [
        group for group in RELEVANT_GROUPS
        if pillar in group.get("content_fit", [])
    ]


def mark_posted(item_id: str, group_post_url: str = "") -> bool:
    """Mark a queue item as posted."""
    try:
        queue = _load_queue()
        for item in queue:
            if item["id"] == item_id:
                item["status"] = "posted"
                item["posted_at"] = datetime.now(timezone.utc).isoformat()
                if group_post_url:
                    item["group_post_url"] = group_post_url
                _save_queue(queue)
                return True
        log.warning(f"Item {item_id} not found in LinkedIn groups queue")
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
