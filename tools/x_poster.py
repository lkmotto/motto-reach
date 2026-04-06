"""
x_poster.py — X (Twitter) Posting Tool
Motto Appraisal Service | Content Distribution Pipeline

Posts content to X using OAuth2 user context.
Auto-posting is gated behind AUTO_POST_X=true env var for safety.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

X_API_BASE = "https://api.twitter.com/2"
USER_TOKEN_PATH = Path("/home/user/workspace/credentials/x_user_token.json")
APP_CREDENTIALS_PATH = Path("/home/user/workspace/credentials/x_oauth.json")

# Rate limit: X API allows 50 posts per 15 min for free tier; be conservative
INTER_TWEET_DELAY_SECONDS = 2


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def get_oauth2_token() -> str:
    """
    Read user access token from x_user_token.json.
    Falls back to app-only bearer token from x_oauth.json if user token unavailable.

    Returns the access token string.
    Raises FileNotFoundError if neither credential file exists.
    """
    # Prefer user-context token (required for posting tweets)
    if USER_TOKEN_PATH.exists():
        with USER_TOKEN_PATH.open() as f:
            data = json.load(f)
        token = data.get("access_token")
        if token:
            return token

    # Fall back to app-only bearer (can read but NOT post tweets)
    if APP_CREDENTIALS_PATH.exists():
        with APP_CREDENTIALS_PATH.open() as f:
            data = json.load(f)
        bearer = data.get("bearer_token")
        if bearer:
            return bearer

    raise FileNotFoundError(
        "No X API credentials found.\n"
        f"  User token: {USER_TOKEN_PATH}\n"
        f"  App credentials: {APP_CREDENTIALS_PATH}\n"
        "Run the OAuth2 flow to generate credentials and save them at the paths above."
    )


def _get_headers() -> dict[str, str]:
    token = get_oauth2_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Core posting functions
# ---------------------------------------------------------------------------

def post_tweet(text: str, reply_to_id: Optional[str] = None) -> dict:
    """
    Post a single tweet.

    Args:
        text: Tweet text (max 280 characters).
        reply_to_id: If provided, post as a reply to this tweet ID.

    Returns:
        {"id": str, "text": str, "url": str}

    Raises:
        ValueError: If tweet text exceeds 280 characters.
        RuntimeError: If the X API returns an error.
    """
    if len(text) > 280:
        raise ValueError(
            f"Tweet text exceeds 280 characters ({len(text)} chars): {text[:80]}..."
        )

    payload: dict = {"text": text}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    response = requests.post(
        f"{X_API_BASE}/tweets",
        headers=_get_headers(),
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"X API error {response.status_code}: {response.text}"
        )

    data = response.json().get("data", {})
    tweet_id = data.get("id", "")
    tweet_text = data.get("text", text)

    return {
        "id": tweet_id,
        "text": tweet_text,
        "url": f"https://x.com/i/web/status/{tweet_id}",
    }


def post_thread(tweets: list[str]) -> list[dict]:
    """
    Post a thread by chaining tweets as replies.

    Args:
        tweets: Ordered list of tweet texts. First tweet is the root.

    Returns:
        List of tweet result dicts [{"id": str, "text": str, "url": str}, ...]

    Raises:
        ValueError: If any tweet exceeds 280 characters.
        RuntimeError: If any X API call fails.
    """
    if not tweets:
        return []

    # Validate all tweets before posting anything
    for i, tweet in enumerate(tweets):
        if len(tweet) > 280:
            raise ValueError(
                f"Tweet {i + 1} exceeds 280 chars ({len(tweet)}): {tweet[:80]}..."
            )

    results: list[dict] = []
    last_id: Optional[str] = None

    for i, tweet_text in enumerate(tweets):
        result = post_tweet(tweet_text, reply_to_id=last_id)
        results.append(result)
        last_id = result["id"]

        # Throttle to avoid hitting rate limits
        if i < len(tweets) - 1:
            time.sleep(INTER_TWEET_DELAY_SECONDS)

    return results


# ---------------------------------------------------------------------------
# Auto-posting gate
# ---------------------------------------------------------------------------

def is_auto_post_enabled() -> bool:
    """Check if AUTO_POST_X env var is set to 'true'."""
    return os.environ.get("AUTO_POST_X", "false").lower() == "true"


def safe_post_tweet(text: str, reply_to_id: Optional[str] = None) -> dict:
    """
    Post a tweet only if AUTO_POST_X=true, otherwise return a dry-run result.

    Returns the actual result dict or a dry-run placeholder.
    """
    if not is_auto_post_enabled():
        return {
            "id": "DRY_RUN",
            "text": text,
            "url": "DRY_RUN — AUTO_POST_X is not enabled",
            "dry_run": True,
        }
    return post_tweet(text, reply_to_id=reply_to_id)


def safe_post_thread(tweets: list[str]) -> list[dict]:
    """
    Post a thread only if AUTO_POST_X=true, otherwise return dry-run results.
    """
    if not is_auto_post_enabled():
        return [
            {
                "id": f"DRY_RUN_{i}",
                "text": tweet,
                "url": f"DRY_RUN — AUTO_POST_X is not enabled (tweet {i + 1})",
                "dry_run": True,
            }
            for i, tweet in enumerate(tweets)
        ]
    return post_thread(tweets)


# ---------------------------------------------------------------------------
# Credential file initializers
# ---------------------------------------------------------------------------

def init_credential_files() -> None:
    """
    Create credential file templates if they don't exist.
    Prompts the user to fill them in with real values.
    """
    USER_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not USER_TOKEN_PATH.exists():
        template = {
            "access_token": "YOUR_OAUTH2_USER_ACCESS_TOKEN",
            "refresh_token": "YOUR_OAUTH2_REFRESH_TOKEN",
            "token_type": "bearer",
            "scope": "tweet.read tweet.write users.read",
            "expires_at": None,
            "_note": (
                "Generated via X OAuth2 PKCE flow. "
                "Required for posting tweets as Luke Motto's account."
            ),
        }
        with USER_TOKEN_PATH.open("w") as f:
            json.dump(template, f, indent=2)
        print(f"Created credential template: {USER_TOKEN_PATH}")

    if not APP_CREDENTIALS_PATH.exists():
        template = {
            "api_key": "YOUR_X_API_KEY",
            "api_secret": "YOUR_X_API_SECRET",
            "bearer_token": "YOUR_X_BEARER_TOKEN",
            "client_id": "YOUR_X_OAUTH2_CLIENT_ID",
            "client_secret": "YOUR_X_OAUTH2_CLIENT_SECRET",
            "_note": (
                "From X Developer Portal → Your App → Keys and Tokens. "
                "Bearer token is for app-only (read-only). "
                "Client ID/Secret are for OAuth2 PKCE user auth flow."
            ),
        }
        with APP_CREDENTIALS_PATH.open("w") as f:
            json.dump(template, f, indent=2)
        print(f"Created app credential template: {APP_CREDENTIALS_PATH}")


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="X posting tool for Motto Appraisal")
    parser.add_argument("--init-creds", action="store_true", help="Initialize credential templates")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be posted without posting")
    parser.add_argument("--tweet", type=str, help="Post a single tweet")
    parser.add_argument("--thread-file", type=str, help="JSON file with list of tweets to post as thread")
    args = parser.parse_args()

    if args.init_creds:
        init_credential_files()

    elif args.dry_run and args.tweet:
        print(f"[DRY RUN] Would post tweet ({len(args.tweet)} chars):")
        print(f"  {args.tweet}")

    elif args.tweet:
        if not is_auto_post_enabled():
            print("AUTO_POST_X is not enabled. Set AUTO_POST_X=true to post.")
            print(f"Would post: {args.tweet}")
        else:
            result = post_tweet(args.tweet)
            print(f"Posted: {result['url']}")

    elif args.thread_file:
        with open(args.thread_file) as f:
            tweets = json.load(f)
        results = safe_post_thread(tweets)
        for r in results:
            print(f"  {'[DRY RUN] ' if r.get('dry_run') else ''}Tweet: {r['url']}")

    else:
        parser.print_help()
