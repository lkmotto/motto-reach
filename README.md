# Motto Appraisal Service — Content Distribution Engine

A complete content distribution pipeline for Luke Motto, licensed DFW real estate appraiser. Takes a LinkedIn post and transforms it into platform-native content for X, Beehiiv, Medium, Substack, Reddit, Facebook Groups, LinkedIn Groups, cold outreach, and SMS — with classification gating, review queuing, and cost tracking.

---

## Architecture

```
motto-distribution/
├── tools/
│   ├── classifier.py        # Content classification (no Claude — rule-based)
│   ├── transformer.py       # Claude claude-sonnet-4-5 generation for all 21 sections
│   ├── x_poster.py          # X (Twitter) OAuth2 posting
│   ├── beehiiv_publisher.py # Beehiiv newsletter drafts
│   └── queue.py             # Local JSON-based content queue
├── agent/
│   └── distributor.py       # Main orchestrator — calls all tools in sequence
├── cron_tracking/
│   ├── distribution_queue.json  # Queue state (auto-created)
│   ├── distribution_log.md      # Run log (auto-created)
│   └── results/                 # Full JSON output per run
├── .env.example             # Environment variable documentation
└── README.md
```

---

## How the Pipeline Works

```
post_data (dict)
    │
    ▼
[1] classifier.classify()
    │  Rule-based. No API calls.
    │  Determines: promotion_risk_level, subreddit_safe,
    │  long_form_safe, recommended_platforms, etc.
    │
    ▼
[2] transformer.transform()
    │  Claude claude-sonnet-4-5-20251101. Generates all 21 sections.
    │  Only populates sections allowed by content_class.
    │  Logs token cost per section.
    │
    ▼
[3] X Posts → queue.py
    │  If AUTO_POST_X=true AND auto_post_x=True → x_poster.safe_post_tweet()
    │  Otherwise → queued with status "skipped"
    │
    ▼
[4] Beehiiv Draft → beehiiv_publisher.create_post(status="draft")
    │  Always draft. Never auto-sent.
    │  Queued with requires_review=True.
    │
    ▼
[5] Review Queue → queue.py (requires_review=True)
    │  LinkedIn Groups, Facebook Groups, Reddit Post, Reddit Comment,
    │  Medium, Substack, LinkedIn Article → all require manual review.
    │
    ▼
[6] Results saved to cron_tracking/results/result_<urn>_<timestamp>.json
    Log appended to cron_tracking/distribution_log.md
```

---

## Setup

### 1. Install dependencies

```bash
cd /home/user/workspace/motto-distribution
pip install anthropic requests
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your API keys
```

Required:
- `ANTHROPIC_API_KEY` — for Claude content generation
- `BEEHIIV_API_KEY` — for newsletter draft creation

### 3. Configure X credentials (if using X posting)

```bash
python tools/x_poster.py --init-creds
```

This creates template files at:
- `/home/user/workspace/credentials/x_user_token.json` — OAuth2 user access token
- `/home/user/workspace/credentials/x_oauth.json` — App credentials

Fill these in with values from the [X Developer Portal](https://developer.twitter.com/en/portal/projects-and-apps).

---

## How to Trigger for a Specific Post

### Option 1: Demo run (no file needed)

```bash
cd /home/user/workspace/motto-distribution
python -m agent.distributor --demo --pillar 1
```

### Option 2: From a JSON file

Create a post file (e.g., `my_post.json`):

```json
{
    "post_urn": "urn:li:activity:7234567890123456789",
    "post_text": "Your LinkedIn post text here...",
    "pillar": 1,
    "format_type": "educational",
    "char_count": 540,
    "published_at": "2025-01-15T14:30:00Z"
}
```

Then run:

```bash
python -m agent.distributor --post-file my_post.json
```

### Option 3: Programmatic (from another script)

```python
from agent.distributor import distribute

post_data = {
    "post_urn": "urn:li:activity:7234567890123456789",
    "post_text": "Your post text...",
    "pillar": 1,
    "format_type": "educational",
    "char_count": 540,
    "published_at": "2025-01-15T14:30:00Z",
}

result = distribute(post_data, auto_post_x=False)
print(f"Cost: ${result['transform_cost']['total_estimated_usd']:.4f}")
print(f"Review items: {len(result['queued']['review_items'])}")
```

---

## Content Pillars

| Pillar | Name | Topics |
|--------|------|--------|
| 1 | Appraiser's Lens | AVM accuracy, what appraisers see that AVMs miss |
| 2 | Deal Math | DSCR, BRRRR, flip vs wholesale vs hold |
| 3 | TX Market Intel | DFW county data, inventory, rate trends |
| 4 | Financing | Hard money vs private money vs DSCR, rate comparisons |
| 5 | Professional's Take | Appraiser observations, market calls |
| 6 | Education | Property tax, how appraisals work, protest process |

---

## How to Review the Manual Queue

### View all items needing review

```bash
python tools/queue.py --review
```

### View queue statistics

```bash
python tools/queue.py --stats
```

### View pending items by platform

```bash
python tools/queue.py --pending --platform reddit
python tools/queue.py --pending --platform linkedin_group
python tools/queue.py --pending --platform facebook_group
```

### Read the full results file

Each run saves a complete JSON file to `cron_tracking/results/`. Open the relevant file to see all 21 generated sections, including the full text for each platform.

### Tail the log

```bash
tail -100 cron_tracking/distribution_log.md
```

---

## How to Enable X Auto-Posting

X auto-posting has a **double-gate** safety system. Both must be true:

1. Set the environment variable:
   ```bash
   export AUTO_POST_X=true
   # or in .env: AUTO_POST_X=true
   ```

2. Pass `auto_post_x=True` when calling distribute:
   ```python
   result = distribute(post_data, auto_post_x=True)
   ```

   Or via CLI:
   ```bash
   python -m agent.distributor --post-file my_post.json --auto-post-x
   ```

**If either condition is false, no tweets are posted.** The content is queued with status `"skipped"` and can be manually posted later.

### X posting behavior

- Individual X posts (from `X_POSTS` section): Posted as standalone tweets.
- X thread (from `X_THREAD` section): Posted as a chained reply thread.
- X replies (from `X_REPLIES` section): Always manual — these are reply snippets for specific conversations.

---

## Reddit Strategy

**Reddit is always manual-only. The engine never auto-posts to Reddit.**

### Why manual-only

Reddit communities detect and penalize promotional content aggressively. Subreddit moderators can permanently ban accounts. Every Reddit post must be reviewed by a human before submission.

### Subreddit selection criteria

The classifier recommends subreddits based on pillar and content, but review these before posting:

| Check | Requirement |
|-------|-------------|
| Promotion risk | Must be `"low"` — no CTAs, no brand mentions |
| Subreddit rules | Read the sidebar. Many subs ban self-promotion entirely. |
| Account history | Post from accounts with subreddit karma history, not brand-new accounts. |
| Framing | Must read as a practitioner sharing experience, not a marketer pitching. |
| No links to mottoappraisal.carrd.co | Reddit treats unfamiliar URLs as spam. |

### Recommended subreddits by pillar

| Pillar | Subreddits |
|--------|-----------|
| 1 — Appraiser's Lens | r/realestateinvesting, r/RealEstate, r/appraisal |
| 2 — Deal Math | r/realestateinvesting, r/financialindependence, r/FIRE |
| 3 — TX Market Intel | r/realestateinvesting, r/DFW, r/Dallas |
| 4 — Financing | r/realestateinvesting, r/Mortgages, r/personalfinance |
| 5 — Professional's Take | r/realestateinvesting, r/RealEstate, r/appraisal |
| 6 — Education | r/RealEstate, r/FirstTimeHomeBuyer, r/personalfinance |

---

## The 21 Output Sections

| # | Section | Auto-post eligible? |
|---|---------|-------------------|
| 1 | CONTENT_CLASSIFICATION | N/A — metadata |
| 2 | PLATFORM_STRATEGY | N/A — strategy |
| 3 | LINKEDIN_POST | Manual |
| 4 | LINKEDIN_ALT_HOOKS | Manual (A/B test) |
| 5 | LINKEDIN_GROUP_VERSION | Manual review required |
| 6 | FACEBOOK_GROUP_VERSION | Manual review required |
| 7 | REDDIT_POST_VERSION | Manual review required |
| 8 | REDDIT_COMMENT_VERSION | Manual review required |
| 9 | X_POSTS | Auto-eligible (gated) |
| 10 | X_THREAD | Auto-eligible (gated) |
| 11 | X_REPLIES | Manual (context-specific) |
| 12 | PINTEREST_PIN | Manual (needs image) |
| 13 | MEDIUM_VERSION | Manual |
| 14 | SUBSTACK_VERSION | Manual |
| 15 | BEEHIIV_VERSION | Auto-draft (never auto-sent) |
| 16 | LINKEDIN_ARTICLE_VERSION | Manual |
| 17 | COMMENT_BANK | Manual (context-specific) |
| 18 | OUTREACH_SNIPPETS | Manual (personalize first) |
| 19 | SMS_TEMPLATES | Manual (consent required) |
| 20 | POSTING_AUTOMATION_NOTES | N/A — guidance |
| 21 | MANUAL_REVIEW_FLAGS | N/A — flags |

---

## SMS Compliance

SMS templates are only generated when `sms_followup_safe=True` (short posts with low promotion risk). Every generated template includes:

- Sender identity: `Luke @ Motto Appraisal`
- Opt-out placeholder: `[Reply STOP to opt out]`
- Character limit enforced: ≤160 chars

**Legal requirement**: Before sending any SMS, verify that each recipient has given explicit written prior consent. Never use these templates for cold outreach.

---

## Cost Tracking

Every run logs Claude API costs. Approximate pricing (claude-sonnet-4-5-20251101):
- Input: $3.00 / 1M tokens
- Output: $15.00 / 1M tokens

A typical full-transform run (all 21 sections) costs approximately **$0.05–$0.15** depending on post length and which sections are generated.

Cost details are logged in:
- `cron_tracking/distribution_log.md` — per-run summary
- `cron_tracking/results/result_*.json` — per-section breakdown in `cost_tracking.calls`

---

## File Locations

| Path | Purpose |
|------|---------|
| `cron_tracking/distribution_queue.json` | Queue state (pending, posted, review) |
| `cron_tracking/distribution_log.md` | Run log |
| `cron_tracking/results/result_*.json` | Full output per run |
| `credentials/x_user_token.json` | X OAuth2 user token |
| `credentials/x_oauth.json` | X app credentials |
