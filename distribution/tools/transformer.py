"""
transformer.py — Platform-Native Content Transformer
Motto Appraisal Service | Content Distribution Pipeline

Given a LinkedIn post + content class, generates platform-native versions
across all 21 output sections using Claude claude-sonnet-4-5-20251101.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-5-20251101"
CTA_URL = "mottoappraisal.carrd.co"

PILLAR_NAMES = {
    1: "Appraiser's Lens",
    2: "Deal Math",
    3: "TX Market Intel",
    4: "Financing",
    5: "Professional's Take",
    6: "Education",
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are writing content for Luke Motto, a licensed real estate appraiser in DFW, Texas.

VOICE RULES (apply to every output):
- Voice: Luke Motto. Direct. Specific. Data-driven. Zero filler.
- Never invent numbers not in the source post. If a stat isn't there, don't fabricate it.
- Never invent URLs. CTA always drives to mottoappraisal.carrd.co or "link in bio".
- Platform X: sharp, punchy, opinionated. Contrarian real estate expert — not motivational speaker.
- Reddit: neutral, helpful, credible. Practitioner sharing experience, not a marketer.
  No self-promotion. No service pitches. Pure signal.
- Newsletters (Beehiiv/Substack): warm but professional. Practitioner newsletter voice.
- Medium/LinkedIn Article: authoritative, evergreen, industry-grade writing.
- Pinterest: functional. Describe processes and checklists clearly. No fluff.
- Facebook Groups: plain language, community-first, conversational.
- Outreach: concise, insight-led. Lead with value, not a pitch.
- SMS: brief, warm, personal. Always include opt-out and sender identity.

ICPs (Ideal Customer Profiles):
DSCR/private lenders, homebuilders, local banks/credit unions, AMCs,
attorneys, property managers, real estate investors.

CONTENT PILLARS:
1. Appraiser's Lens — AVM accuracy, what appraisers see that AVMs miss
2. Deal Math — DSCR, BRRRR, flip vs wholesale vs hold
3. TX Market Intel — DFW county data, inventory, rate trends
4. Financing — hard money vs private money vs DSCR, rate comparisons
5. Professional's Take — appraiser observations, market calls
6. Education — property tax, how appraisals work, protest process
"""

# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Add it to your .env file."
        )
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


def _log_cost(section: str, input_tokens: int, output_tokens: int) -> dict:
    """
    Compute Claude claude-sonnet-4-5 cost approximation.
    Pricing (per million tokens, as of 2025):
      Input:  $3.00 / 1M tokens
      Output: $15.00 / 1M tokens
    """
    input_cost = (input_tokens / 1_000_000) * 3.00
    output_cost = (output_tokens / 1_000_000) * 15.00
    return {
        "section": section,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": round(input_cost + output_cost, 6),
    }


# ---------------------------------------------------------------------------
# Generation helpers
# ---------------------------------------------------------------------------


def _call_claude(
    client: anthropic.Anthropic, prompt: str, max_tokens: int = 2000
) -> tuple[str, dict]:
    """
    Single Claude call. Returns (response_text, cost_dict).
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text if response.content else ""
    usage = response.usage
    cost = _log_cost("call", usage.input_tokens, usage.output_tokens)
    return text, cost


def _call_claude_json(
    client: anthropic.Anthropic,
    prompt: str,
    fallback: Any = None,
    max_tokens: int = 2000,
) -> tuple[Any, dict]:
    """
    Call Claude and attempt to parse the response as JSON.
    Returns (parsed_object, cost_dict).
    """
    text, cost = _call_claude(
        client,
        prompt + "\n\nRespond with valid JSON only. No markdown fences.",
        max_tokens,
    )
    try:
        # Strip potential markdown code fences
        clean = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean), cost
    except (json.JSONDecodeError, ValueError):
        return fallback, cost


# ---------------------------------------------------------------------------
# Section generators (one per section that uses Claude)
# ---------------------------------------------------------------------------


def _gen_linkedin_post(client, post_text: str, pillar: int) -> tuple[str, dict]:
    prompt = (
        f"Clean and polish the following LinkedIn post for Luke Motto (Pillar {pillar}: "
        f"{PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Fix any typos or awkward phrasing. Preserve the original voice and data.\n"
        "- Keep line breaks. Keep the structure.\n"
        "- Do NOT add a CTA if one isn't already present.\n"
        "- Return ONLY the cleaned post text.\n\n"
        f"ORIGINAL POST:\n{post_text}"
    )
    return _call_claude(client, prompt, max_tokens=1000)


def _gen_linkedin_alt_hooks(
    client, post_text: str, pillar: int
) -> tuple[list[str], dict]:
    prompt = (
        f"Write 3 alternative first-line hooks for this LinkedIn post (Pillar {pillar}: "
        f"{PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Each hook must:\n"
        "- Be a single sentence (max 120 chars)\n"
        "- Create curiosity or make a bold claim using data already in the post\n"
        "- Sound like Luke Motto: direct, specific, no fluff\n\n"
        "Return a JSON array of 3 strings.\n\n"
        f"POST:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback=[], max_tokens=400)
    if isinstance(result, list):
        return result[:3], cost
    return [], cost


def _gen_linkedin_group_version(
    client, post_text: str, pillar: int
) -> tuple[str, dict]:
    prompt = (
        f"Rewrite this LinkedIn post for a LinkedIn professional group (Pillar {pillar}: "
        f"{PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Remove promotional language and direct CTAs\n"
        "- Make it educational and community-oriented\n"
        "- End with a discussion question to the group\n"
        "- Preserve all data points from the original\n"
        "- Voice: Luke Motto, but collegial not promotional\n\n"
        "⚠️ FLAG: This version requires manual review before posting.\n\n"
        f"ORIGINAL POST:\n{post_text}"
    )
    return _call_claude(client, prompt, max_tokens=800)


def _gen_facebook_group_version(
    client, post_text: str, pillar: int
) -> tuple[str, dict]:
    prompt = (
        f"Rewrite this post for a local real estate Facebook group (Pillar {pillar}: "
        f"{PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Plain, conversational language (Facebook skews less professional than LinkedIn)\n"
        "- Community-first framing — 'I've been seeing this a lot lately...'\n"
        "- No promotional language or direct CTAs\n"
        "- Keep all data from the original\n"
        "- End with a question to invite responses\n\n"
        "⚠️ FLAG: This version requires manual review before posting.\n\n"
        f"ORIGINAL POST:\n{post_text}"
    )
    return _call_claude(client, prompt, max_tokens=800)


def _gen_reddit_post(
    client, post_text: str, pillar: int, subreddits: list[str]
) -> tuple[dict, dict]:
    sub_hint = ", ".join(subreddits[:2]) if subreddits else "r/realestateinvesting"
    prompt = (
        f"Write a Reddit text post for {sub_hint} based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "CRITICAL Reddit rules:\n"
        "- Zero self-promotion. Zero brand mentions. Zero CTAs.\n"
        "- Sound like a practitioner sharing a real observation, not a marketer\n"
        "- Neutral, helpful, credible tone\n"
        "- Title must be informative (not clickbait)\n"
        "- Body must provide standalone value\n"
        "- Use markdown (bullet points, **bold** for emphasis)\n\n"
        "Return JSON with keys: title (str), body (str), suggested_flair (str)\n\n"
        f"SOURCE CONTENT:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=1200)
    if not isinstance(result, dict):
        result = {}
    return result, cost


def _gen_reddit_comment(client, post_text: str, pillar: int) -> tuple[str, dict]:
    prompt = (
        f"Write a Reddit comment-style contribution for a relevant thread, based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Answer-style. Write as if you're responding to someone's question in a thread.\n"
        "- No self-promotion or brand mentions.\n"
        "- Sound like a knowledgeable practitioner, not a marketer.\n"
        "- Keep it under 300 words.\n\n"
        f"SOURCE CONTENT:\n{post_text}"
    )
    return _call_claude(client, prompt, max_tokens=600)


def _gen_x_posts(client, post_text: str, pillar: int) -> tuple[list[str], dict]:
    prompt = (
        f"Write 4 standalone X (Twitter) posts based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Max 280 chars each\n"
        "- Sharp, punchy, opinionated — contrarian real estate expert voice\n"
        "- Each post must stand alone (no context needed from others)\n"
        "- Use data and specific numbers from the source when possible\n"
        "- Never motivational. Never generic. Specific insight only.\n"
        "- No hashtag spam — max 1-2 relevant hashtags if any\n\n"
        "Return a JSON array of 4 strings.\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback=[], max_tokens=800)
    if isinstance(result, list):
        # Enforce 280 char limit
        trimmed = [t[:280] for t in result if isinstance(t, str)]
        return trimmed[:5], cost
    return [], cost


def _gen_x_thread(client, post_text: str, pillar: int) -> tuple[list[str], dict]:
    prompt = (
        f"Write a 7-tweet X (Twitter) thread based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Tweet 1: bold hook that stops the scroll\n"
        "- Tweets 2-6: one clear point each. Each tweet standalone-readable.\n"
        "- Tweet 7: conclusion + soft CTA (link in bio / mottoappraisal.carrd.co)\n"
        "- Max 280 chars each\n"
        "- Number format: '1/' '2/' etc.\n"
        "- Sharp, opinionated, data-driven voice\n\n"
        "Return a JSON array of 7 strings.\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback=[], max_tokens=1200)
    if isinstance(result, list):
        trimmed = [t[:280] for t in result if isinstance(t, str)]
        return trimmed[:8], cost
    return [], cost


def _gen_x_replies(client, post_text: str, pillar: int) -> tuple[list[str], dict]:
    prompt = (
        f"Write 3 reply-style X (Twitter) snippets based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- These are designed to be replies to relevant conversations\n"
        "- Sound like you're adding value to a thread, not promoting\n"
        "- Max 280 chars each\n"
        "- Direct, sharp, specific insight\n\n"
        "Return a JSON array of 3 strings.\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback=[], max_tokens=600)
    if isinstance(result, list):
        trimmed = [t[:280] for t in result if isinstance(t, str)]
        return trimmed[:3], cost
    return [], cost


def _gen_pinterest_pin(client, post_text: str, pillar: int) -> tuple[dict, dict]:
    prompt = (
        f"Create a Pinterest pin based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Functional and specific. Describe a process, checklist, or data visual.\n"
        "- Title: keyword-rich, specific, 50-60 chars\n"
        "- Description: 200-300 chars, SEO-friendly, actionable\n"
        "- Text overlay: short headline for the pin image (max 10 words)\n"
        "- Board suggestion: where this pin belongs\n"
        "- Destination URL: mottoappraisal.carrd.co\n\n"
        "Return JSON with keys: title, description, text_overlay, board_suggestion, destination_url\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=600)
    if not isinstance(result, dict):
        result = {}
    result.setdefault("destination_url", f"https://{CTA_URL}")
    return result, cost


def _gen_medium_version(client, post_text: str, pillar: int) -> tuple[dict, dict]:
    prompt = (
        f"Write a full Medium article based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Evergreen framing — written to be useful in 6 months\n"
        "- Professional, authoritative tone\n"
        "- Title: compelling, SEO-aware\n"
        "- Subtitle: clarifies scope / audience\n"
        "- Body: use H2 headings, structured paragraphs, 600-900 words\n"
        "- CTA at end: drives to mottoappraisal.carrd.co\n"
        "- Excerpt: 2-sentence preview for Medium discovery feed\n\n"
        "Return JSON with keys: title, subtitle, body_markdown, cta, excerpt\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=2500)
    if not isinstance(result, dict):
        result = {}
    return result, cost


def _gen_substack_version(client, post_text: str, pillar: int) -> tuple[dict, dict]:
    prompt = (
        f"Write a Substack newsletter post based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Editorial voice — like a practitioner writing to their readers\n"
        "- Warmer and more conversational than Medium, but still professional\n"
        "- Begin with a personal framing or recent observation\n"
        "- Subject line: newsletter-style (e.g. 'What I saw in Collin County last week')\n"
        "- Body: 400-600 words, flowing prose, some structure\n"
        "- CTA: drive to subscribe or to mottoappraisal.carrd.co\n\n"
        "Return JSON with keys: subject_line, body_markdown, cta\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=2000)
    if not isinstance(result, dict):
        result = {}
    return result, cost


def _gen_beehiiv_version(client, post_text: str, pillar: int) -> tuple[dict, dict]:
    prompt = (
        f"Write a Beehiiv email newsletter post based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Email-first format — will be sent directly to subscribers\n"
        "- Warm but professional. Practitioner newsletter voice.\n"
        "- Subject line: email-optimized (curiosity + specificity, under 50 chars)\n"
        "- Preview text: email preview snippet (max 90 chars)\n"
        "- Body: HTML-friendly markdown, 300-500 words\n"
        "- CTA button text: short action phrase (e.g. 'Book a Call', 'See Our Services')\n"
        "- CTA URL: mottoappraisal.carrd.co\n\n"
        "Return JSON with keys: subject_line, preview_text, body_markdown, cta_button_text, cta_url\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=2000)
    if not isinstance(result, dict):
        result = {}
    result.setdefault("cta_url", f"https://{CTA_URL}")
    return result, cost


def _gen_linkedin_article_version(
    client, post_text: str, pillar: int
) -> tuple[dict, dict]:
    prompt = (
        f"Write a professional LinkedIn Article based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- More formal than a LinkedIn post — industry article standard\n"
        "- Written for professionals: lenders, investors, builders\n"
        "- Title: thought-leadership framing\n"
        "- Body: H2 sections, 700-1000 words, evergreen\n"
        "- Byline: 'Luke Motto, Licensed Real Estate Appraiser, DFW Texas'\n"
        "- CTA: professional, non-pushy — 'Connect with me on LinkedIn or visit mottoappraisal.carrd.co'\n\n"
        "Return JSON with keys: title, byline, body_markdown, cta\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=2500)
    if not isinstance(result, dict):
        result = {}
    return result, cost


def _gen_comment_bank(client, post_text: str, pillar: int) -> tuple[list[dict], dict]:
    prompt = (
        f"Write 5 platform-specific comments for Luke Motto to use on LinkedIn and Reddit/X, "
        f"based on this content (Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Comments should add value to relevant conversations — not promote\n"
        "- 3 for LinkedIn: professional, insight-adding\n"
        "- 2 for Reddit or X: neutral, practitioner-style\n"
        "- Each comment should be usable standalone (no context needed)\n"
        "- Max 200 chars for Reddit/X, 400 chars for LinkedIn\n\n"
        "Return JSON array where each item has: platform (str), comment_text (str)\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback=[], max_tokens=1200)
    if isinstance(result, list):
        return result[:5], cost
    return [], cost


def _gen_outreach_snippets(client, post_text: str, pillar: int) -> tuple[dict, dict]:
    prompt = (
        f"Write outreach snippets for Luke Motto based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "Rules:\n"
        "- Lead with the insight or data point — value first, pitch never\n"
        "- Cold email: 3 versions (50-80 words each). Subject line + body.\n"
        "- LinkedIn DM: 2 versions (2-3 sentences each). Conversational.\n"
        "- Call talking points: 2 bullet-point talking points for a warm call\n\n"
        "Return JSON with keys:\n"
        "  cold_emails: list of {subject, body}\n"
        "  linkedin_dms: list of str\n"
        "  call_talking_points: list of str\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=1500)
    if not isinstance(result, dict):
        result = {}
    return result, cost


def _gen_sms_templates(client, post_text: str, pillar: int) -> tuple[list[dict], dict]:
    prompt = (
        f"Write 2 warm follow-up SMS templates for Luke Motto based on this content "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        "COMPLIANCE RULES (mandatory):\n"
        "- Must include sender identity: 'Luke @ Motto Appraisal'\n"
        "- Must include opt-out placeholder: '[Reply STOP to opt out]'\n"
        "- Max 160 chars each (including identity and opt-out)\n"
        "- Assumes explicit prior consent — warm follow-up context only\n"
        "- Personal, direct, not promotional\n\n"
        "Return JSON array where each item has: template_text (str), char_count (int)\n\n"
        f"SOURCE:\n{post_text}"
    )
    result, cost = _call_claude_json(client, prompt, fallback=[], max_tokens=600)
    if isinstance(result, list):
        # Validate char counts
        validated = []
        for item in result[:2]:
            if isinstance(item, dict):
                text = item.get("template_text", "")
                item["char_count"] = len(text)
                validated.append(item)
        return validated, cost
    return [], cost


def _gen_platform_strategy(
    client, post_text: str, pillar: int, content_class: dict
) -> tuple[dict, dict]:
    platforms = content_class.get("recommended_platforms", [])
    risk = content_class.get("promotion_risk_level", "low")
    prompt = (
        f"Write a concise platform distribution strategy for this post "
        f"(Pillar {pillar}: {PILLAR_NAMES.get(pillar, 'Real Estate')}).\n\n"
        f"Recommended platforms: {', '.join(platforms) if platforms else 'linkedin, x'}\n"
        f"Promotion risk level: {risk}\n\n"
        "For each platform, provide:\n"
        "- Rationale (1 sentence)\n"
        "- Recommended posting order (numbered)\n"
        "- Timing suggestion\n\n"
        "Return JSON with keys:\n"
        "  ordered_platforms: list of platform names (in posting order)\n"
        "  rationale: dict mapping platform name to 1-sentence rationale\n"
        "  timing_notes: str\n\n"
        f"POST SUMMARY:\n{post_text[:400]}"
    )
    result, cost = _call_claude_json(client, prompt, fallback={}, max_tokens=800)
    if not isinstance(result, dict):
        result = {}
    return result, cost


# ---------------------------------------------------------------------------
# Main transform function
# ---------------------------------------------------------------------------


def transform(post: dict, content_class: dict, pillar: int) -> dict:  # noqa: C901
    """
    Given a LinkedIn post + content class, generate all 21 output sections.

    Args:
        post: dict with at minimum 'post_text' key
        content_class: output from classifier.classify()
        pillar: int 1–6

    Returns:
        dict with all 21 section keys, plus 'cost_tracking' list
    """
    client = _get_client()
    post_text: str = post.get("post_text", "")
    costs: list[dict] = []
    output: dict[str, Any] = {}

    def _track(section_name: str, result: Any, cost: dict) -> Any:
        cost["section"] = section_name
        costs.append(cost)
        return result

    # 1. CONTENT_CLASSIFICATION (from classifier — no Claude call)
    output["CONTENT_CLASSIFICATION"] = content_class

    # 2. PLATFORM_STRATEGY
    platform_strategy, cost = _gen_platform_strategy(
        client, post_text, pillar, content_class
    )
    output["PLATFORM_STRATEGY"] = _track("PLATFORM_STRATEGY", platform_strategy, cost)

    # 3. LINKEDIN_POST (clean version)
    linkedin_post, cost = _gen_linkedin_post(client, post_text, pillar)
    output["LINKEDIN_POST"] = _track("LINKEDIN_POST", linkedin_post, cost)

    # 4. LINKEDIN_ALT_HOOKS
    alt_hooks, cost = _gen_linkedin_alt_hooks(client, post_text, pillar)
    output["LINKEDIN_ALT_HOOKS"] = _track("LINKEDIN_ALT_HOOKS", alt_hooks, cost)

    # 5. LINKEDIN_GROUP_VERSION (requires manual review)
    if content_class.get("group_safe"):
        lg_version, cost = _gen_linkedin_group_version(client, post_text, pillar)
        output["LINKEDIN_GROUP_VERSION"] = _track(
            "LINKEDIN_GROUP_VERSION", lg_version, cost
        )
        output["LINKEDIN_GROUP_VERSION_REVIEW_FLAG"] = True
    else:
        output["LINKEDIN_GROUP_VERSION"] = None
        output["LINKEDIN_GROUP_VERSION_REVIEW_FLAG"] = False

    # 6. FACEBOOK_GROUP_VERSION (requires manual review)
    if content_class.get("group_safe"):
        fb_version, cost = _gen_facebook_group_version(client, post_text, pillar)
        output["FACEBOOK_GROUP_VERSION"] = _track(
            "FACEBOOK_GROUP_VERSION", fb_version, cost
        )
        output["FACEBOOK_GROUP_VERSION_REVIEW_FLAG"] = True
    else:
        output["FACEBOOK_GROUP_VERSION"] = None
        output["FACEBOOK_GROUP_VERSION_REVIEW_FLAG"] = False

    # 7. REDDIT_POST_VERSION (requires manual review)
    if content_class.get("subreddit_safe"):
        reddit_post, cost = _gen_reddit_post(
            client, post_text, pillar, content_class.get("recommended_subreddits", [])
        )
        output["REDDIT_POST_VERSION"] = _track("REDDIT_POST_VERSION", reddit_post, cost)
        output["REDDIT_POST_REVIEW_FLAG"] = True
    else:
        output["REDDIT_POST_VERSION"] = None
        output["REDDIT_POST_REVIEW_FLAG"] = False

    # 8. REDDIT_COMMENT_VERSION (requires manual review)
    if content_class.get("subreddit_safe"):
        reddit_comment, cost = _gen_reddit_comment(client, post_text, pillar)
        output["REDDIT_COMMENT_VERSION"] = _track(
            "REDDIT_COMMENT_VERSION", reddit_comment, cost
        )
        output["REDDIT_COMMENT_REVIEW_FLAG"] = True
    else:
        output["REDDIT_COMMENT_VERSION"] = None
        output["REDDIT_COMMENT_REVIEW_FLAG"] = False

    # 9. X_POSTS
    if content_class.get("public_feed_safe"):
        x_posts, cost = _gen_x_posts(client, post_text, pillar)
        output["X_POSTS"] = _track("X_POSTS", x_posts, cost)
    else:
        output["X_POSTS"] = []

    # 10. X_THREAD
    if content_class.get("public_feed_safe") and content_class.get("long_form_safe"):
        x_thread, cost = _gen_x_thread(client, post_text, pillar)
        output["X_THREAD"] = _track("X_THREAD", x_thread, cost)
    elif content_class.get("public_feed_safe"):
        # Generate a shorter thread anyway if content warrants it
        x_thread, cost = _gen_x_thread(client, post_text, pillar)
        output["X_THREAD"] = _track("X_THREAD", x_thread, cost)
    else:
        output["X_THREAD"] = []

    # 11. X_REPLIES
    if content_class.get("public_feed_safe"):
        x_replies, cost = _gen_x_replies(client, post_text, pillar)
        output["X_REPLIES"] = _track("X_REPLIES", x_replies, cost)
    else:
        output["X_REPLIES"] = []

    # 12. PINTEREST_PIN (for educational/checklist content)
    if pillar in {1, 2, 6} and content_class.get("public_feed_safe"):
        pinterest, cost = _gen_pinterest_pin(client, post_text, pillar)
        output["PINTEREST_PIN"] = _track("PINTEREST_PIN", pinterest, cost)
    else:
        output["PINTEREST_PIN"] = None

    # 13. MEDIUM_VERSION
    if content_class.get("long_form_safe"):
        medium, cost = _gen_medium_version(client, post_text, pillar)
        output["MEDIUM_VERSION"] = _track("MEDIUM_VERSION", medium, cost)
    else:
        output["MEDIUM_VERSION"] = None

    # 14. SUBSTACK_VERSION
    if content_class.get("long_form_safe"):
        substack, cost = _gen_substack_version(client, post_text, pillar)
        output["SUBSTACK_VERSION"] = _track("SUBSTACK_VERSION", substack, cost)
    else:
        output["SUBSTACK_VERSION"] = None

    # 15. BEEHIIV_VERSION (always generate if educational or data-rich)
    if content_class.get("long_form_safe") or content_class.get(
        "outreach_snippet_safe"
    ):
        beehiiv, cost = _gen_beehiiv_version(client, post_text, pillar)
        output["BEEHIIV_VERSION"] = _track("BEEHIIV_VERSION", beehiiv, cost)
    else:
        output["BEEHIIV_VERSION"] = None

    # 16. LINKEDIN_ARTICLE_VERSION
    if content_class.get("long_form_safe"):
        li_article, cost = _gen_linkedin_article_version(client, post_text, pillar)
        output["LINKEDIN_ARTICLE_VERSION"] = _track(
            "LINKEDIN_ARTICLE_VERSION", li_article, cost
        )
    else:
        output["LINKEDIN_ARTICLE_VERSION"] = None

    # 17. COMMENT_BANK
    comment_bank, cost = _gen_comment_bank(client, post_text, pillar)
    output["COMMENT_BANK"] = _track("COMMENT_BANK", comment_bank, cost)

    # 18. OUTREACH_SNIPPETS
    if content_class.get("outreach_snippet_safe"):
        outreach, cost = _gen_outreach_snippets(client, post_text, pillar)
        output["OUTREACH_SNIPPETS"] = _track("OUTREACH_SNIPPETS", outreach, cost)
    else:
        output["OUTREACH_SNIPPETS"] = None

    # 19. SMS_TEMPLATES
    if content_class.get("sms_followup_safe"):
        sms, cost = _gen_sms_templates(client, post_text, pillar)
        output["SMS_TEMPLATES"] = _track("SMS_TEMPLATES", sms, cost)
    else:
        output["SMS_TEMPLATES"] = []

    # 20. POSTING_AUTOMATION_NOTES
    output["POSTING_AUTOMATION_NOTES"] = _build_automation_notes(content_class, output)

    # 21. MANUAL_REVIEW_FLAGS
    output["MANUAL_REVIEW_FLAGS"] = _build_manual_review_flags(content_class, output)

    # Cost summary
    total_cost = sum(c.get("estimated_cost_usd", 0) for c in costs)
    total_input = sum(c.get("input_tokens", 0) for c in costs)
    total_output = sum(c.get("output_tokens", 0) for c in costs)
    output["cost_tracking"] = {
        "model": MODEL,
        "calls": costs,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_estimated_cost_usd": round(total_cost, 6),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    return output


# ---------------------------------------------------------------------------
# Helper builders for sections 20 and 21
# ---------------------------------------------------------------------------


def _build_automation_notes(content_class: dict, output: dict) -> dict:
    """Section 20: Classify each section as auto-post eligible or manual-only."""
    notes: dict[str, str] = {}

    notes["LINKEDIN_POST"] = (
        "AUTO-POST eligible"
        if content_class.get("public_feed_safe")
        else "MANUAL REVIEW required before posting"
    )
    notes["LINKEDIN_ALT_HOOKS"] = (
        "MANUAL — use for A/B testing. Select one before posting."
    )
    notes["LINKEDIN_GROUP_VERSION"] = (
        "MANUAL REVIEW required — must be reviewed before posting to any group"
        if content_class.get("group_safe")
        else "NOT GENERATED — content not group_safe"
    )
    notes["FACEBOOK_GROUP_VERSION"] = (
        "MANUAL REVIEW required — group moderators may remove promotional content"
        if content_class.get("group_safe")
        else "NOT GENERATED — content not group_safe"
    )
    notes["REDDIT_POST_VERSION"] = (
        "MANUAL REVIEW required — Reddit will detect and ban promotional content"
        if content_class.get("subreddit_safe")
        else "NOT GENERATED — content not subreddit_safe"
    )
    notes["REDDIT_COMMENT_VERSION"] = (
        "MANUAL REVIEW required — use only in relevant active threads"
        if content_class.get("subreddit_safe")
        else "NOT GENERATED"
    )

    x_posts_status = output.get("X_POSTS", [])
    notes["X_POSTS"] = (
        "AUTO-POST eligible (gated by AUTO_POST_X env var). Review char limits before enabling."
        if x_posts_status
        else "NOT GENERATED"
    )
    notes["X_THREAD"] = (
        "AUTO-POST eligible for threads via x_poster.post_thread(). Gated by AUTO_POST_X."
        if output.get("X_THREAD")
        else "NOT GENERATED"
    )
    notes["X_REPLIES"] = "MANUAL — deploy as replies to relevant conversations only."
    notes["PINTEREST_PIN"] = (
        "MANUAL — requires image creation before posting."
        if output.get("PINTEREST_PIN")
        else "NOT GENERATED"
    )
    notes["MEDIUM_VERSION"] = (
        "MANUAL — format in Medium editor before publishing."
        if output.get("MEDIUM_VERSION")
        else "NOT GENERATED"
    )
    notes["SUBSTACK_VERSION"] = (
        "MANUAL — publish via Substack dashboard."
        if output.get("SUBSTACK_VERSION")
        else "NOT GENERATED"
    )
    notes["BEEHIIV_VERSION"] = (
        "AUTO-DRAFT via beehiiv_publisher.create_post(). Never auto-sent. Review before confirming."
        if output.get("BEEHIIV_VERSION")
        else "NOT GENERATED"
    )
    notes["LINKEDIN_ARTICLE_VERSION"] = "MANUAL — publish via LinkedIn Articles editor."
    notes["COMMENT_BANK"] = "MANUAL — deploy selectively in relevant comment threads."
    notes["OUTREACH_SNIPPETS"] = (
        "MANUAL — personalize before sending. These are templates only."
        if output.get("OUTREACH_SNIPPETS")
        else "NOT GENERATED"
    )
    notes["SMS_TEMPLATES"] = (
        "MANUAL — requires explicit prior consent. Verify consent before sending."
        if output.get("SMS_TEMPLATES")
        else "NOT GENERATED — content not sms_followup_safe"
    )

    return notes


def _build_manual_review_flags(content_class: dict, output: dict) -> list[dict]:
    """Section 21: Consolidated list of items requiring manual review."""
    flags: list[dict] = []

    def _flag(section: str, reason: str, priority: str = "medium") -> None:
        flags.append({"section": section, "reason": reason, "priority": priority})

    risk = content_class.get("promotion_risk_level", "low")

    if risk == "high":
        _flag(
            "ALL_SECTIONS",
            "Post has high promotion risk. Review all variants before distributing anywhere.",
            "high",
        )
    elif risk == "medium":
        _flag(
            "LINKEDIN_POST",
            "Post contains promotional language. Review CTA phrasing before public posting.",
            "medium",
        )

    if output.get("LINKEDIN_GROUP_VERSION_REVIEW_FLAG"):
        _flag(
            "LINKEDIN_GROUP_VERSION",
            "Group posts carry risk of being flagged as promotional. Review framing and remove any CTAs.",
            "high",
        )

    if output.get("FACEBOOK_GROUP_VERSION_REVIEW_FLAG"):
        _flag(
            "FACEBOOK_GROUP_VERSION",
            "Facebook group admins can ban promotional content. Verify community rules before posting.",
            "high",
        )

    if output.get("REDDIT_POST_REVIEW_FLAG"):
        _flag(
            "REDDIT_POST_VERSION",
            "Reddit auto-removes promotional content. Verify zero brand mentions and no CTAs before submitting.",
            "high",
        )

    if output.get("REDDIT_COMMENT_REVIEW_FLAG"):
        _flag(
            "REDDIT_COMMENT_VERSION",
            "Only use in threads where this adds genuine value. Do not deploy unsolicited.",
            "medium",
        )

    sms_templates = output.get("SMS_TEMPLATES", [])
    if sms_templates:
        _flag(
            "SMS_TEMPLATES",
            "LEGAL: Verify explicit written consent exists for every recipient before sending any SMS.",
            "high",
        )

    outreach = output.get("OUTREACH_SNIPPETS")
    if outreach:
        _flag(
            "OUTREACH_SNIPPETS",
            "Personalize all snippets before sending. Generic outreach reduces response rates.",
            "low",
        )

    pinterest = output.get("PINTEREST_PIN")
    if pinterest:
        _flag(
            "PINTEREST_PIN",
            "Image/graphic must be created separately — this only provides copy and structure.",
            "low",
        )

    return flags


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from tools.classifier import classify

    sample_post = {
        "post_urn": "urn:li:activity:test001",
        "post_text": (
            "AVM said $420k. My appraisal came in at $387k.\n\n"
            "The delta? A 450 sq ft unpermitted addition with mismatched flooring "
            "that Zillow's model will never catch.\n\n"
            "AVMs read square footage and zip code. They don't read condition, "
            "effective age, or deferred maintenance.\n\n"
            "That 8% gap costs buyers real money and lenders real risk.\n\n"
            "If you're underwriting DSCR loans in DFW, here's what to watch for:\n"
            "• Permitted vs unpermitted additions\n"
            "• Pool condition adjustments\n"
            "• Functional obsolescence from dated floor plans\n\n"
            "AVM confidence scores are not appraiser sign-offs."
        ),
        "pillar": 1,
        "format_type": "educational",
        "published_at": "2025-01-01T12:00:00Z",
    }

    cc = classify(sample_post)
    result = transform(sample_post, cc, pillar=1)

    output_path = "/home/user/workspace/motto-distribution/cron_tracking/test_transform_output.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Transform complete. Output saved to: {output_path}")
    print(
        f"Total estimated cost: ${result['cost_tracking']['total_estimated_cost_usd']:.4f}"
    )
