"""
x_client.py — X/Twitter browser automation for reply outreach
No API needed — uses Playwright with saved session.
Session file: data/x_session.json (needs to be created via login)

X strategy: Reply to intent posts ONLY (no DMs — requires $100/mo API).
Replies are public, build your profile, zero ban risk vs DMs.
"""
import json, time, random, logging, os
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

log = logging.getLogger("x")
SESSION_FILE = Path(__file__).parent / "data" / "x_session.json"

X_USERNAME = os.getenv("X_USERNAME", "mottoappraisal")
X_PASSWORD = os.getenv("X_PASSWORD", "")

# Search queries that find high-intent posts
INTENT_QUERIES = [
    "need appraiser DFW",
    "home appraisal Fort Worth OR Dallas OR Roanoke",
    "DSCR loan Texas appraiser",
    "property tax protest DCAD OR TCAD",
    "pre-listing appraisal Texas",
    "appraisal came in low Texas",
    "divorce appraisal Texas",
    "PMI removal appraisal",
    "BRRRR refinance appraisal",
    "home appraisal Keller OR Southlake OR Trophy Club",
]

HIGH_INTENT_X = [
    "need appraiser", "appraisal", "home value", "house worth",
    "dscr", "brrrr", "arv", "pmi removal", "heloc", "refi",
    "tax protest", "dcad", "tcad", "pre-listing", "divorce home",
]

DFW_GEO_X = [
    "dfw", "dallas", "fort worth", "tarrant", "denton",
    "keller", "southlake", "roanoke", "trophy club", "north texas",
]

# Daily ramp: start conservative, increase over 2 weeks
def daily_x_limit(days_running: int) -> int:
    if days_running <= 3: return 8
    if days_running <= 7: return 15
    if days_running <= 14: return 20
    return 25


def login(page) -> bool:
    """Log in to X/Twitter. Returns True on success."""
    if not X_PASSWORD:
        log.error("X_PASSWORD env var not set")
        return False

    log.info(f"Logging in to X as @{X_USERNAME}...")
    page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    try:
        # Username step
        page.locator('input[autocomplete="username"], input[name="text"]').first.fill(X_USERNAME)
        time.sleep(0.5)
        page.locator('button:has-text("Next"), [data-testid="LoginForm_Login_Button"]').first.click()
        time.sleep(2)

        # Sometimes asks for phone/email verification — enter username again
        try:
            verify_box = page.locator('input[data-testid="ocfEnterTextTextInput"]').first
            if verify_box.is_visible(timeout=3000):
                verify_box.fill(X_USERNAME)
                page.locator('button:has-text("Next")').first.click()
                time.sleep(2)
        except PWTimeout:
            pass

        # Password step
        page.locator('input[name="password"], input[type="password"]').first.fill(X_PASSWORD)
        time.sleep(0.5)
        page.locator('button:has-text("Log in"), [data-testid="LoginForm_Login_Button"]').first.click()
        time.sleep(3)

        # Verify
        if "home" in page.url or "x.com" in page.url and "login" not in page.url:
            cookies = page.context.cookies()
            SESSION_FILE.parent.mkdir(exist_ok=True)
            SESSION_FILE.write_text(json.dumps(cookies))
            log.info("X login successful, session saved")
            return True

    except Exception as e:
        log.error(f"X login error: {e}")
    return False


def _load_session(context) -> bool:
    if SESSION_FILE.exists():
        context.add_cookies(json.loads(SESSION_FILE.read_text()))
        return True
    return False


def _score_tweet(text: str, is_dfw: bool = False) -> int:
    lower = text.lower()
    sc = sum(10 for s in HIGH_INTENT_X if s in lower)
    sc += sum(8 for s in DFW_GEO_X if s in lower)
    if is_dfw: sc += 5
    if "?" in text: sc += 5
    return sc


def scan_x(seen_ids: set) -> list:
    """Search X for intent-signal posts. Returns list of tweet dicts."""
    if not SESSION_FILE.exists():
        log.warning("No X session — cannot scan. Run login first.")
        return []

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width":1280,"height":800}
        )
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        _load_session(context)
        page = context.new_page()

        for query in INTENT_QUERIES[:5]:  # Limit to 5 queries per cycle
            try:
                encoded = query.replace(" ", "%20").replace('"', '%22')
                page.goto(f"https://x.com/search?q={encoded}&f=live",
                         wait_until="domcontentloaded", timeout=20000)
                time.sleep(random.uniform(2, 3))

                # Scroll to load tweets
                page.mouse.wheel(0, 800)
                time.sleep(1.5)

                # Extract tweets
                tweets = page.evaluate("""
                    () => {
                        const results = [];
                        document.querySelectorAll('article[data-testid="tweet"]').forEach(el => {
                            const textEl = el.querySelector('[data-testid="tweetText"]');
                            const linkEl = el.querySelector('a[href*="/status/"]');
                            const userEl = el.querySelector('[data-testid="User-Name"] a');
                            if (textEl && linkEl) {
                                const href = linkEl.href;
                                const idMatch = href.match(/status\\/([0-9]+)/);
                                results.push({
                                    id: idMatch ? idMatch[1] : href,
                                    text: textEl.innerText,
                                    url: href,
                                    username: userEl ? userEl.href.split('/').pop() : ''
                                });
                            }
                        });
                        return results;
                    }
                """)

                for tweet in tweets:
                    tid = tweet.get("id", "")
                    if not tid or tid in seen_ids: continue
                    if tweet.get("username") == X_USERNAME: continue  # Skip own tweets

                    sc = _score_tweet(tweet["text"])
                    if sc < 10: continue

                    seen_ids.add(tid)
                    results.append({
                        "id": tid,
                        "platform": "x",
                        "text": tweet["text"][:300],
                        "url": tweet["url"],
                        "username": tweet["username"],
                        "score": sc,
                        "query": query,
                    })
                    log.info(f"  X hit [{sc}pts] @{tweet['username']}: {tweet['text'][:55]}")

                time.sleep(random.uniform(3, 6))

            except Exception as e:
                log.warning(f"X search '{query}': {e}")

        browser.close()

    log.info(f"X scan complete: {len(results)} targets")
    return results


def reply_to_tweet(tweet_url: str, reply_text: str) -> bool:
    """Post a reply to a tweet."""
    if not SESSION_FILE.exists():
        log.warning("No X session")
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width":1280,"height":800}
        )
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        _load_session(context)
        page = context.new_page()

        try:
            page.goto(tweet_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(2.5, 4))

            # Click reply button
            reply_btn = page.locator('[data-testid="reply"]').first
            reply_btn.click()
            time.sleep(random.uniform(1, 2))

            # Type reply
            reply_box = page.locator('[data-testid="tweetTextarea_0"], '
                                     'div[role="textbox"][data-testid*="reply"]').first
            reply_box.click()
            for char in reply_text:
                page.keyboard.type(char)
                time.sleep(random.uniform(0.02, 0.05))
            time.sleep(random.uniform(0.8, 1.5))

            # Submit
            page.locator('[data-testid="tweetButtonInline"]').first.click()
            time.sleep(random.uniform(2, 3))

            log.info(f"X reply posted: {tweet_url[:60]}")
            return True

        except Exception as e:
            log.error(f"X reply failed: {e}")
            return False
        finally:
            browser.close()
