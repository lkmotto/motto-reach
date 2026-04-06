"""
x_poster.py — X (Twitter) posting tool using OAuth1.0a

Credentials stored at /home/user/workspace/credentials/x_oauth1.json:
  consumer_key, consumer_secret, access_token, access_token_secret

IMPORTANT: The X app must have OAuth1.0a enabled in Developer Portal
under User authentication settings > OAuth 1.0a. Access tokens must be
regenerated AFTER enabling Read+Write permissions.

If OAuth1 fails (401), check:
1. App settings → Authentication → App permissions = Read and Write
2. App settings → Authentication → Type of App = Web App / Automated / Bot
3. Regenerate access token & secret after permission change
4. Enable "OAuth 1.0a" explicitly in User authentication settings
"""

import json, os, logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

CREDS_PATH = Path("/home/user/workspace/credentials/x_oauth1.json")
AUTO_POST_X = os.environ.get("AUTO_POST_X", "false").lower() == "true"
MAX_TWEET_LENGTH = 280


def _get_oauth_session():
    """Return an authenticated requests_oauthlib.OAuth1Session."""
    try:
        from requests_oauthlib import OAuth1Session
        creds = json.loads(CREDS_PATH.read_text())
        return OAuth1Session(
            client_key=creds["consumer_key"],
            client_secret=creds["consumer_secret"],
            resource_owner_key=creds["access_token"],
            resource_owner_secret=creds["access_token_secret"],
        )
    except Exception as e:
        log.error(f"OAuth session error: {e}")
        return None


def verify_credentials() -> Optional[dict]:
    """Return account info if credentials are valid, None otherwise."""
    session = _get_oauth_session()
    if not session:
        return None
    r = session.get("https://api.twitter.com/1.1/account/verify_credentials.json")
    if r.ok:
        d = r.json()
        return {"screen_name": d.get("screen_name"), "id": d.get("id_str")}
    log.error(f"Credential verification failed: {r.status_code} {r.text[:200]}")
    return None


def post_tweet(text: str, reply_to_id: str = None) -> dict:
    """
    Post a tweet via X API v2 with OAuth1 user context.
    Returns: {"id": str, "text": str, "url": str, "success": bool}
    """
    if len(text) > MAX_TWEET_LENGTH:
        text = text[:MAX_TWEET_LENGTH - 3] + "..."

    session = _get_oauth_session()
    if not session:
        return {"success": False, "error": "Could not create OAuth session"}

    body = {"text": text}
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    r = session.post("https://api.twitter.com/2/tweets", json=body)

    if r.ok:
        data = r.json()["data"]
        tweet_id = data["id"]
        url = f"https://x.com/mottoappraisal/status/{tweet_id}"
        log.info(f"Tweet posted: {url}")
        return {"id": tweet_id, "text": data["text"], "url": url, "success": True}
    else:
        log.error(f"Tweet failed: {r.status_code} {r.text[:300]}")
        return {"success": False, "error": r.text[:300], "status_code": r.status_code}


def post_thread(tweets: list[str]) -> list[dict]:
    """Post a thread by chaining replies. Returns list of result dicts."""
    results = []
    reply_to = None
    for i, text in enumerate(tweets):
        result = post_tweet(text, reply_to_id=reply_to)
        results.append(result)
        if result.get("success"):
            reply_to = result["id"]
        else:
            log.warning(f"Thread broke at tweet {i+1}: {result.get('error')}")
            break
    return results


def safe_post_tweet(text: str) -> dict:
    """Post only if AUTO_POST_X=true. Otherwise log and return queued status."""
    if not AUTO_POST_X:
        log.info(f"AUTO_POST_X=false — tweet queued for manual review: {text[:80]}...")
        return {"success": False, "queued": True, "reason": "AUTO_POST_X not enabled"}
    return post_tweet(text)
