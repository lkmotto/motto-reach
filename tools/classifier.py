"""
classifier.py — Content Classification Engine
Motto Appraisal Service | Content Distribution Pipeline

Given a LinkedIn post dict, classify it into ContentClass fields
that gate which platforms and formats can safely receive the content.
"""

from __future__ import annotations

import re
from typing import TypedDict


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

class ContentClass(TypedDict):
    public_feed_safe: bool           # OK for LinkedIn/X/Facebook public
    group_safe: bool                 # OK for LinkedIn/Facebook groups (less promotional)
    subreddit_safe: bool             # Could fit in a subreddit (educational, not marketing)
    long_form_safe: bool             # Has enough depth for Medium/Substack/Beehiiv article
    short_form_video_safe: bool      # Could become a 15–30 s video script
    outreach_snippet_safe: bool      # Contains a hook or insight usable in cold outreach
    sms_followup_safe: bool          # Could work as a warm follow-up after prior contact
    promotion_risk_level: str        # "low" | "medium" | "high"
    manual_review_required: bool
    recommended_subreddits: list[str]
    recommended_platforms: list[str]


# ---------------------------------------------------------------------------
# Subreddit map by pillar
# ---------------------------------------------------------------------------

PILLAR_SUBREDDITS: dict[int, list[str]] = {
    1: [
        "r/realestateinvesting",
        "r/RealEstate",
        "r/FirstTimeHomeBuyer",
        "r/appraisal",
    ],
    2: [
        "r/realestateinvesting",
        "r/passive_income",
        "r/financialindependence",
        "r/FIRE",
    ],
    3: [
        "r/realestateinvesting",
        "r/texas",
        "r/Dallas",
        "r/DFW",
    ],
    4: [
        "r/realestateinvesting",
        "r/personalfinance",
        "r/RealEstateInvesting",
        "r/Mortgages",
    ],
    5: [
        "r/realestateinvesting",
        "r/RealEstate",
        "r/appraisal",
    ],
    6: [
        "r/RealEstate",
        "r/FirstTimeHomeBuyer",
        "r/personalfinance",
        "r/texas",
    ],
}

# Regex patterns for detection
_DOLLAR_RE = re.compile(r"\$[\d,]+|\d+[\s]?(?:dollars?|USD)", re.IGNORECASE)
_PERCENT_RE = re.compile(r"\d+\.?\d*\s?%")
_CTA_RE = re.compile(
    r"\b(book\s+a\s+call|schedule|contact\s+me|link\s+in\s+bio|DM\s+me|"
    r"reach\s+out|apply\s+now|get\s+a\s+quote|click\s+here|sign\s+up|"
    r"subscribe|visit|mottoappraisal|carrd\.co)\b",
    re.IGNORECASE,
)
_SERVICE_RE = re.compile(
    r"\b(appraisal\s+service|appraisal\s+report|hire\s+me|my\s+service|"
    r"we\s+offer|I\s+provide|order\s+an\s+appraisal|get\s+an\s+appraisal|"
    r"working\s+with\s+me|my\s+firm|our\s+firm)\b",
    re.IGNORECASE,
)

# Pillars whose data-rich content is subreddit safe
_EDUCATIONAL_PILLARS = {1, 2, 3, 6}


def _has_dollars_or_pct(text: str) -> bool:
    return bool(_DOLLAR_RE.search(text) or _PERCENT_RE.search(text))


def _has_cta(text: str) -> bool:
    return bool(_CTA_RE.search(text))


def _has_service_mention(text: str) -> bool:
    return bool(_SERVICE_RE.search(text))


def _has_specific_data(text: str) -> bool:
    """True when post contains numbers, percentages, or named stats."""
    return bool(
        _DOLLAR_RE.search(text)
        or _PERCENT_RE.search(text)
        or re.search(r"\b\d{4}\b", text)          # years / specific numbers
        or re.search(r"\d+[\s]?(?:units|homes|listings|days)", text, re.I)
    )


def _count_points(text: str) -> int:
    """Rough count of distinct bullet points or numbered items."""
    bullets = re.findall(r"(?m)^[\s]*[-•*▸]\s+\S", text)
    numbered = re.findall(r"(?m)^\s*\d+[.)]\s+\S", text)
    return len(bullets) + len(numbered)


# ---------------------------------------------------------------------------
# Subreddit recommendation helper
# ---------------------------------------------------------------------------

def _recommend_subreddits(pillar: int, text: str, subreddit_safe: bool) -> list[str]:
    if not subreddit_safe:
        return []
    base = list(PILLAR_SUBREDDITS.get(pillar, ["r/realestateinvesting"]))
    # Add geography hints if DFW is mentioned
    if re.search(r"\b(DFW|Dallas|Fort Worth|Tarrant|Collin|Denton|Frisco|McKinney)\b", text, re.I):
        for sub in ["r/DFW", "r/Dallas"]:
            if sub not in base:
                base.append(sub)
    return base[:4]  # cap at 4


# ---------------------------------------------------------------------------
# Platform recommendation helper
# ---------------------------------------------------------------------------

def _recommend_platforms(
    public_feed_safe: bool,
    long_form_safe: bool,
    subreddit_safe: bool,
    promotion_risk_level: str,
) -> list[str]:
    platforms: list[str] = []
    if public_feed_safe:
        platforms.extend(["linkedin", "x"])
    if long_form_safe:
        platforms.extend(["medium", "substack", "beehiiv"])
    if subreddit_safe and promotion_risk_level == "low":
        platforms.append("reddit")
    if public_feed_safe and promotion_risk_level in ("low", "medium"):
        platforms.append("facebook_groups")
        platforms.append("linkedin_groups")
    # Pinterest makes sense for checklist / process pillars
    # Pillar 6 (Education) and Pillar 2 (Deal Math) translate well
    return list(dict.fromkeys(platforms))  # deduplicate, preserve order


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify(post: dict) -> ContentClass:
    """
    Classify a LinkedIn post dict into a ContentClass.

    Expected keys in post:
        post_text   : str   — full text of the post
        pillar      : int   — 1–6 content pillar number
        char_count  : int   — character count (computed if absent)
        format_type : str   — e.g. "educational", "data", "opinion", "promo"
    """
    text: str = post.get("post_text", "")
    pillar: int = int(post.get("pillar", 1))
    char_count: int = post.get("char_count") or len(text)
    format_type: str = (post.get("format_type") or "").lower()

    has_cta = _has_cta(text)
    has_service = _has_service_mention(text)
    has_data = _has_specific_data(text)
    has_dollars_pct = _has_dollars_or_pct(text)
    point_count = _count_points(text)
    is_educational_pillar = pillar in _EDUCATIONAL_PILLARS

    # ---- promotion_risk_level ------------------------------------------------
    if has_service and has_cta:
        promotion_risk_level = "high"
    elif has_cta or has_service:
        promotion_risk_level = "medium"
    elif format_type == "promo":
        promotion_risk_level = "medium"
    else:
        promotion_risk_level = "low"

    # ---- public_feed_safe ----------------------------------------------------
    # All posts are public-feed-safe unless extreme promotional content
    public_feed_safe = promotion_risk_level != "high"

    # ---- group_safe ----------------------------------------------------------
    # OK unless high-promotion or explicit service pitch
    group_safe = not has_service and promotion_risk_level != "high"

    # ---- subreddit_safe ------------------------------------------------------
    # Educational pillars with specific data, no CTA, no service mention
    subreddit_safe = (
        is_educational_pillar
        and has_data
        and not has_cta
        and not has_service
        and promotion_risk_level == "low"
    )

    # ---- long_form_safe ------------------------------------------------------
    # >800 chars AND multiple points or a longer format type
    long_form_safe = char_count > 800 and (point_count >= 2 or len(text.split()) > 150)

    # ---- short_form_video_safe -----------------------------------------------
    # Concrete tip, comparison, or data point that condenses into 15–30 s
    short_form_video_safe = (
        has_data
        and char_count <= 1200
        and pillar in {1, 2, 3, 4, 6}
    )

    # ---- outreach_snippet_safe -----------------------------------------------
    # Has a compelling data hook (dollars / percentages)
    outreach_snippet_safe = has_dollars_pct

    # ---- sms_followup_safe ---------------------------------------------------
    # Short-to-medium posts with a single actionable insight
    sms_followup_safe = (
        char_count <= 600
        and promotion_risk_level == "low"
        and (has_data or format_type in ("educational", "tip"))
    )

    # ---- manual_review_required ----------------------------------------------
    # Anything that touches groups/Reddit or has medium/high promo risk
    manual_review_required = (
        group_safe             # group versions need human eyes
        or subreddit_safe      # Reddit requires practitioner framing
        or promotion_risk_level in ("medium", "high")
    )

    recommended_subreddits = _recommend_subreddits(pillar, text, subreddit_safe)
    recommended_platforms = _recommend_platforms(
        public_feed_safe, long_form_safe, subreddit_safe, promotion_risk_level
    )

    return ContentClass(
        public_feed_safe=public_feed_safe,
        group_safe=group_safe,
        subreddit_safe=subreddit_safe,
        long_form_safe=long_form_safe,
        short_form_video_safe=short_form_video_safe,
        outreach_snippet_safe=outreach_snippet_safe,
        sms_followup_safe=sms_followup_safe,
        promotion_risk_level=promotion_risk_level,
        manual_review_required=manual_review_required,
        recommended_subreddits=recommended_subreddits,
        recommended_platforms=recommended_platforms,
    )


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    sample = {
        "post_text": (
            "AVM said $420k. My appraisal came in at $387k.\n\n"
            "The delta? A 450 sq ft addition with no permit and mismatched flooring "
            "that Zillow's model will never catch.\n\n"
            "AVMs read square footage and zip code. They don't read condition, "
            "effective age, or deferred maintenance.\n\n"
            "That 8% gap costs buyers real money and it costs lenders real risk.\n\n"
            "If you're underwriting DSCR loans in DFW, here's what to watch for:\n"
            "• Permitted vs unpermitted additions\n"
            "• Pool condition adjustments\n"
            "• Functional obsolescence from dated floor plans\n\n"
            "AVM confidence scores are not appraiser sign-offs."
        ),
        "pillar": 1,
        "format_type": "educational",
    }

    result = classify(sample)
    print(json.dumps(result, indent=2))
