"""
reddit_client.py — Playwright-based Reddit client using saved session cookie
Session: /home/user/workspace/motto-reddit/fast_session.json (valid Oct 2026)
"""

import json
import time
import random
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

log = logging.getLogger("reddit")
SESSION_FILE = Path("/home/user/workspace/motto-reddit/fast_session.json")

# Subreddits where comments are acceptable (no strict spam rules)
COMMENT_OK = {
    "FirstTimeHomeBuyer",
    "personalfinance",
    "appraisal",
    "RealEstate",
    "HousingMarket",
    "texasrealestate",
    "DFWRealEstate",
}

HIGH_INTENT = [
    "need an appraiser",
    "recommend an appraiser",
    "find an appraiser",
    "home appraisal",
    "house appraisal",
    "property appraisal",
    "appraisal came in",
    "appraisal low",
    "appraisal high",
    "appraisal gap",
    "dscr loan",
    "dscr appraisal",
    "form 1007",
    "rental income appraisal",
    "divorce appraisal",
    "estate appraisal",
    "probate appraisal",
    "date of death",
    "pre-listing appraisal",
    "tax protest appraisal",
    "property tax protest",
    "dcad",
    "tcad",
    "pmi removal",
    "remove pmi",
    "heloc appraisal",
    "cash out refi",
    "refinance appraisal",
    "after repair value",
    "arv appraisal",
    "brrrr refinance",
    "low appraisal",
    "fight appraisal",
    "dispute appraisal",
]

DFW_GEO = [
    "dfw",
    "dallas",
    "fort worth",
    "tarrant county",
    "denton county",
    "collin county",
    "trophy club",
    "roanoke tx",
    "keller tx",
    "southlake tx",
    "frisco tx",
    "north texas",
    "texas home",
    "tx appraiser",
    "texas real estate",
]

SUBREDDITS = [
    "realestateinvesting",
    "RealEstate",
    "FirstTimeHomeBuyer",
    "appraisal",
    "dfw",
    "fortworth",
    "personalfinance",
    "DFWRealEstate",
    "texasrealestate",
    "HousingMarket",
]


def _score(title: str, body: str = "") -> tuple:
    full = (title + " " + body).lower()
    intent_hits = [s for s in HIGH_INTENT if s in full]
    geo_hits = [s for s in DFW_GEO if s in full]
    sc = len(intent_hits) * 10 + len(geo_hits) * 8
    if "?" in title:
        sc += 8
    if any(
        w in title.lower()
        for w in ["help", "need", "recommend", "looking", "advice", "suggest", "anyone"]
    ):
        sc += 8
    return sc, intent_hits, geo_hits


def _make_context(pw):
    context = pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    ).new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/Chicago",
    )
    context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
    )
    if SESSION_FILE.exists():
        context.add_cookies(json.loads(SESSION_FILE.read_text()))
    return context


def scan_subreddits(seen_ids: set) -> list:
    """
    Scan all subreddits for intent-signal posts not already seen.
    Returns list of qualifying post dicts.
    """
    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};"
        )
        if SESSION_FILE.exists():
            context.add_cookies(json.loads(SESSION_FILE.read_text()))

        page = context.new_page()

        for sub in SUBREDDITS:
            try:
                page.goto(
                    f"https://www.reddit.com/r/{sub}/new.json?limit=25&raw_json=1",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                time.sleep(random.uniform(0.8, 1.5))

                raw = page.locator("pre, body").first.inner_text()
                posts = json.loads(raw).get("data", {}).get("children", [])

                for p in posts:
                    d = p["data"]
                    pid = d["id"]
                    if pid in seen_ids:
                        continue
                    if d.get("author") in ("[deleted]", "AutoModerator"):
                        continue

                    age_hrs = (time.time() - d.get("created_utc", 0)) / 3600
                    if age_hrs > 72:
                        continue

                    sc, intent_hits, geo_hits = _score(
                        d["title"], d.get("selftext", "")
                    )

                    # Require at least one actual intent signal (not just geo)
                    if sc < 16 or not intent_hits:
                        continue

                    results.append(
                        {
                            "id": pid,
                            "subreddit": sub,
                            "title": d["title"],
                            "body": d.get("selftext", "")[:500],
                            "author": d["author"],
                            "url": f"https://www.reddit.com{d['permalink']}",
                            "created_utc": d.get("created_utc", 0),
                            "age_hours": round(age_hrs, 1),
                            "score": sc,
                            "intent": intent_hits,
                            "dfw": bool(geo_hits),
                            "comment_ok": sub in COMMENT_OK,
                        }
                    )
                    log.info(
                        f"  [{sc}pts] {'[DFW]' if geo_hits else '     '} r/{sub}: {d['title'][:60]}"
                    )

                time.sleep(random.uniform(1.0, 2.5))

            except Exception as e:
                log.warning(f"r/{sub}: {e}")

        browser.close()

    log.info(f"Scan complete: {len(results)} qualifying posts")
    return results


def check_inbox() -> list:
    """Check Reddit inbox for new replies. Returns list of reply dicts."""
    replies = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1366, "height": 768},
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        if SESSION_FILE.exists():
            context.add_cookies(json.loads(SESSION_FILE.read_text()))

        page = context.new_page()
        try:
            page.goto(
                "https://www.reddit.com/message/inbox.json?limit=25",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            time.sleep(1)
            raw = page.locator("pre, body").first.inner_text()
            messages = json.loads(raw).get("data", {}).get("children", [])
            for m in messages:
                d = m["data"]
                if not d.get("new", False):
                    continue  # Only unread
                replies.append(
                    {
                        "id": d.get("id"),
                        "author": d.get("author"),
                        "subject": d.get("subject", ""),
                        "body": d.get("body", "")[:500],
                        "context": d.get("context", ""),
                        "created_utc": d.get("created_utc", 0),
                    }
                )
        except Exception as e:
            log.warning(f"Inbox check error: {e}")
        finally:
            browser.close()

    return replies


def send_dm(username: str, message: str) -> bool:
    if not username or username in ("[deleted]", "AutoModerator"):
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};"
        )
        if SESSION_FILE.exists():
            context.add_cookies(json.loads(SESSION_FILE.read_text()))

        page = context.new_page()
        try:
            page.goto(
                f"https://www.reddit.com/message/compose/?to={username}",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            time.sleep(random.uniform(2, 3))

            page.locator('input[name="message-title"]').first.fill("Re: your post")
            time.sleep(random.uniform(0.3, 0.6))

            msg_box = page.locator(
                '#innerTextArea, textarea[name="message-content"]'
            ).first
            if not msg_box.is_visible(timeout=5000):
                log.warning(f"No message box for u/{username}")
                return False

            for char in message:
                msg_box.type(char)
                time.sleep(random.uniform(0.02, 0.05))
            time.sleep(random.uniform(0.8, 1.5))

            page.locator('button[type="submit"]').first.click()
            time.sleep(random.uniform(2, 3))

            body = page.locator("body").inner_text().lower()
            if "ratelimit" in body or "too many messages" in body:
                log.warning(f"Rate limited sending DM to u/{username}")
                return False

            log.info(f"DM sent to u/{username}")
            return True

        except Exception as e:
            log.error(f"DM to u/{username} failed: {e}")
            return False
        finally:
            browser.close()


def post_comment(post_url: str, text: str) -> bool:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};"
        )
        if SESSION_FILE.exists():
            context.add_cookies(json.loads(SESSION_FILE.read_text()))

        page = context.new_page()
        try:
            page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(2.5, 4))

            # Scroll down to load the comment box
            page.mouse.wheel(0, 600)
            time.sleep(1.5)

            # Click the comment area to activate it
            comment_box = page.locator(
                'div[contenteditable="true"][class*="cursor-text"], '
                'div[contenteditable="true"][class*="DraftEditor"], '
                ".public-DraftEditor-content, "
                'div[role="textbox"][contenteditable="true"]'
            ).first

            if not comment_box.is_visible(timeout=8000):
                # Try clicking "Leave a comment" button first
                try:
                    page.locator(
                        'button:has-text("Leave a comment"), '
                        'button:has-text("Add a comment")'
                    ).first.click(timeout=3000)
                    time.sleep(1)
                    comment_box = page.locator('div[contenteditable="true"]').first
                except Exception:
                    pass

            comment_box.click()
            time.sleep(0.5)

            for char in text:
                page.keyboard.type(char)
                time.sleep(random.uniform(0.015, 0.04))
            time.sleep(random.uniform(1.5, 2.5))

            # Submit
            page.locator('button:has-text("Comment")').first.click()
            time.sleep(random.uniform(2, 3))
            log.info(f"Comment posted: {post_url[:60]}")
            return True

        except Exception as e:
            log.error(f"Comment failed on {post_url[:60]}: {e}")
            return False
        finally:
            browser.close()
