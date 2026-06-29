"""
beehiiv_publisher.py — Beehiiv Newsletter Tool
Motto Appraisal Service | Content Distribution Pipeline

Manages newsletter posts, subscribers, and drafts via the Beehiiv v2 API.
Posts are ALWAYS created as drafts — never auto-sent.
"""

from __future__ import annotations
import sys as _sys  # noqa: E402
import pathlib as _pathlib  # noqa: E402

_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
from motto_common.sentry_init import init_sentry  # was: import sentry_init
init_sentry(agent_name="motto-distribution")

import os
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BEEHIIV_API = "https://api.beehiiv.com/v2"
PUB_ID = "pub_6b0e21de-3244-40cb-a06c-b56c603e28fc"

# Safety: Beehiiv posts from this engine are always created as drafts.
# Set status="confirmed" manually in the Beehiiv dashboard, never programmatically.
_DEFAULT_STATUS = "draft"


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    api_key = os.environ.get("BEEHIIV_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "BEEHIIV_API_KEY environment variable is not set. Add it to your .env file."
        )
    return api_key


def _get_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _handle_response(response: requests.Response, operation: str) -> dict:
    """Raise with context if Beehiiv API returns an error."""
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Beehiiv API error during {operation}: "
            f"HTTP {response.status_code} — {response.text}"
        )
    return response.json()


# ---------------------------------------------------------------------------
# Core API functions
# ---------------------------------------------------------------------------


def create_post(
    subject: str,
    preview_text: str,
    body_html: str,
    status: str = _DEFAULT_STATUS,
    scheduled_at: Optional[str] = None,
) -> dict:
    """
    Create a newsletter post on Beehiiv.

    ⚠️  Safety: This function should ONLY be called with status="draft".
    The distributor pipeline enforces this. Do not change the default.

    Args:
        subject: Email subject line.
        preview_text: Email preview/preheader text (shown in inbox before open).
        body_html: Full HTML body of the newsletter.
        status: "draft" (default, safe) or "confirmed" (sends immediately — use manually only).
        scheduled_at: ISO8601 datetime string to schedule the post (optional).

    Returns:
        {"id": str, "status": str, "web_url": str, "created_at": str}

    Raises:
        RuntimeError: If the Beehiiv API returns an error.
    """
    # Enforce draft safety
    if status not in ("draft", "confirmed"):
        raise ValueError(f"Invalid status '{status}'. Must be 'draft' or 'confirmed'.")

    if status == "confirmed":
        import warnings

        warnings.warn(
            "⚠️  Creating a 'confirmed' Beehiiv post will SEND it immediately to all subscribers. "
            "This should only be done manually after review, not via automated pipeline.",
            UserWarning,
            stacklevel=2,
        )

    payload: dict = {
        "publication_id": PUB_ID,
        "subject_line": subject,
        "preview_text": preview_text,
        "content_json": None,  # Using HTML body
        "content_html": body_html,
        "status": status,
    }

    if scheduled_at:
        payload["scheduled_at"] = scheduled_at

    response = requests.post(
        f"{BEEHIIV_API}/publications/{PUB_ID}/posts",
        headers=_get_headers(),
        json=payload,
        timeout=30,
    )

    data = _handle_response(response, "create_post")
    post_data = data.get("data", data)

    return {
        "id": post_data.get("id", ""),
        "status": post_data.get("status", status),
        "web_url": post_data.get("web_url") or post_data.get("url", ""),
        "created_at": post_data.get("created_at", ""),
        "subject": subject,
    }


def get_post(post_id: str) -> dict:
    """
    Retrieve a single post by ID.

    Returns:
        Post dict with full metadata.
    """
    response = requests.get(
        f"{BEEHIIV_API}/publications/{PUB_ID}/posts/{post_id}",
        headers=_get_headers(),
        timeout=30,
    )
    data = _handle_response(response, f"get_post({post_id})")
    return data.get("data", data)


def get_subscribers(limit: int = 100) -> list[dict]:
    """
    Get active subscribers list.

    Args:
        limit: Max subscribers to return (API default is 100, max is 100 per page).

    Returns:
        List of subscriber dicts with email, name, status, created_at.
    """
    params = {
        "status": "active",
        "limit": min(limit, 100),
    }

    response = requests.get(
        f"{BEEHIIV_API}/publications/{PUB_ID}/subscriptions",
        headers=_get_headers(),
        params=params,
        timeout=30,
    )

    data = _handle_response(response, "get_subscribers")
    subscribers = data.get("data", [])

    # Normalize subscriber objects
    return [
        {
            "id": sub.get("id", ""),
            "email": sub.get("email", ""),
            "name": sub.get("name", ""),
            "status": sub.get("status", "active"),
            "created_at": sub.get("created_at", ""),
        }
        for sub in subscribers
    ]


def add_subscriber(email: str, name: Optional[str] = None) -> dict:
    """
    Add a new subscriber programmatically.

    ⚠️  Only use for subscribers who have given explicit consent.

    Args:
        email: Subscriber email address.
        name: Subscriber's name (optional).

    Returns:
        {"id": str, "email": str, "status": str, "created_at": str}
    """
    payload: dict = {
        "email": email,
        "reactivate_existing": False,
        "send_welcome_email": True,
    }
    if name:
        payload["name"] = name

    response = requests.post(
        f"{BEEHIIV_API}/publications/{PUB_ID}/subscriptions",
        headers=_get_headers(),
        json=payload,
        timeout=30,
    )

    data = _handle_response(response, f"add_subscriber({email})")
    sub_data = data.get("data", data)

    return {
        "id": sub_data.get("id", ""),
        "email": sub_data.get("email", email),
        "status": sub_data.get("status", "pending"),
        "created_at": sub_data.get("created_at", ""),
    }


def list_posts(status: str = "draft", limit: int = 20) -> list[dict]:
    """
    List posts filtered by status.

    Args:
        status: "draft", "confirmed", "archived"
        limit: Max posts to return.

    Returns:
        List of post summary dicts.
    """
    params = {
        "status": status,
        "limit": min(limit, 100),
        "order_by": "created_at",
        "direction": "desc",
    }

    response = requests.get(
        f"{BEEHIIV_API}/publications/{PUB_ID}/posts",
        headers=_get_headers(),
        params=params,
        timeout=30,
    )

    data = _handle_response(response, f"list_posts(status={status})")
    posts = data.get("data", [])

    return [
        {
            "id": p.get("id", ""),
            "subject": p.get("subject_line", ""),
            "status": p.get("status", ""),
            "web_url": p.get("web_url", ""),
            "created_at": p.get("created_at", ""),
        }
        for p in posts
    ]


def markdown_to_html(markdown_text: str) -> str:
    """
    Convert markdown to basic HTML for Beehiiv body.
    Handles: headers, bold, lists, paragraphs, line breaks.
    """
    import re

    html = markdown_text

    # Headers
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)

    # Italic
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

    # Bullet lists
    lines = html.split("\n")
    result_lines = []
    in_list = False
    for line in lines:
        if re.match(r"^[-•*] (.+)", line):
            if not in_list:
                result_lines.append("<ul>")
                in_list = True
            result_lines.append(f"  <li>{re.sub(r'^[-•*] ', '', line)}</li>")
        else:
            if in_list:
                result_lines.append("</ul>")
                in_list = False
            result_lines.append(line)
    if in_list:
        result_lines.append("</ul>")
    html = "\n".join(result_lines)

    # Paragraph wrapping (double newlines)
    paragraphs = re.split(r"\n{2,}", html)
    wrapped = []
    for p in paragraphs:
        p = p.strip()
        if (
            p
            and not p.startswith("<h")
            and not p.startswith("<ul")
            and not p.startswith("</ul")
        ):
            p = f"<p>{p}</p>"
        wrapped.append(p)
    html = "\n".join(wrapped)

    # Clean up empty paragraphs
    html = re.sub(r"<p>\s*</p>", "", html)

    return html


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sentry_sdk as _sentry_sdk

    try:
        import argparse

        parser = argparse.ArgumentParser(
            description="Beehiiv publisher for Motto Appraisal"
        )
        parser.add_argument(
            "--list-drafts", action="store_true", help="List current draft posts"
        )
        parser.add_argument(
            "--list-subscribers", action="store_true", help="List active subscribers"
        )
        parser.add_argument(
            "--sub-count", action="store_true", help="Show subscriber count"
        )
        args = parser.parse_args()

        if args.list_drafts:
            drafts = list_posts(status="draft")
            print(f"Draft posts ({len(drafts)}):")
            for d in drafts:
                print(f"  [{d['id']}] {d['subject']} — {d['created_at']}")

        elif args.list_subscribers:
            subs = get_subscribers(limit=100)
            print(f"Active subscribers ({len(subs)}):")
            for s in subs[:10]:
                print(f"  {s['email']} — {s['name'] or 'No name'}")
            if len(subs) > 10:
                print(f"  ... and {len(subs) - 10} more")

        elif args.sub_count:
            subs = get_subscribers(limit=100)
            print(f"Active subscribers: {len(subs)}")

        else:
            parser.print_help()
    except Exception as _exc:
        _sentry_sdk.capture_exception(_exc)
        raise
