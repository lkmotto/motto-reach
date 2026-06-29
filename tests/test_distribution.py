"""
Tests for motto-reach distribution/ package.

Covers classifier.py (pure logic, no API calls) and queue.py (local JSON queue).
"""
import sys
import json
from pathlib import Path

import pytest

# Ensure distribution/ is on sys.path so "tools.classifier" resolves
_DIST_DIR = Path(__file__).parent.parent / "distribution"
if str(_DIST_DIR) not in sys.path:
    sys.path.insert(0, str(_DIST_DIR))

from tools.classifier import (  # noqa: E402
    classify,
    _has_cta,
    _has_service_mention,
    _has_dollars_or_pct,
    _has_specific_data,
    _count_points,
    _recommend_subreddits,
    _recommend_platforms,
    PILLAR_SUBREDDITS,
    ContentClass,
)
from tools.queue import (  # noqa: E402
    add_to_queue,
    get_pending,
    mark_posted,
    mark_failed,
    mark_skipped,
    get_review_queue,
    get_all,
    get_item,
    get_stats,
    clear_posted,
    VALID_PLATFORMS,
    STATUS_PENDING,
    STATUS_REVIEW,
    STATUS_POSTED,
    STATUS_FAILED,
    STATUS_SKIPPED,
)
import tools.queue as queue_mod  # noqa: E402 - for monkeypatching QUEUE_PATH


# ---------------------------------------------------------------------------
# Sample post_data for classifier tests
# ---------------------------------------------------------------------------

EDUCATIONAL_POST = {
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
}

PROMOTIONAL_POST = {
    "post_text": (
        "Need an appraisal in DFW? Book a call with me today! "
        "We offer the best appraisal service in Dallas. "
        "Click here to schedule your appraisal now."
    ),
    "pillar": 5,
    "format_type": "promo",
    "char_count": 160,
}

SHORT_TIP_POST = {
    "post_text": "Check your property tax assessment. DCAD values are up 12% this year.",
    "pillar": 6,
    "format_type": "tip",
    "char_count": 78,
}


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


class TestImports:
    """Verify that distribution packages and key symbols are importable."""

    def test_tools_package_imports(self):
        """tools package exists and has expected modules."""
        import tools  # noqa: F401
        import tools.classifier  # noqa: F401
        import tools.queue  # noqa: F401

    def test_classifier_symbols_exist(self):
        """classify function and its helpers are importable."""
        assert callable(classify)
        assert callable(_has_cta)
        assert callable(_has_service_mention)
        assert callable(_has_dollars_or_pct)
        assert callable(_has_specific_data)
        assert callable(_count_points)

    def test_queue_symbols_exist(self):
        """Queue public API functions are importable."""
        assert callable(add_to_queue)
        assert callable(get_stats)


# ---------------------------------------------------------------------------
# classifier.py - Regex helpers
# ---------------------------------------------------------------------------


class TestRegexHelpers:
    """Tests for the pattern-matching helper functions in classifier.py."""

    def test_has_cta_detects_call_to_action(self):
        assert _has_cta("Book a call with me today") is True
        assert _has_cta("Click here to get started") is True
        assert _has_cta("DM me for details") is True
        assert _has_cta("Visit mottoappraisal.carrd.co") is True

    def test_has_cta_rejects_non_cta(self):
        assert _has_cta("Here is some market analysis") is False
        assert _has_cta("AVM confidence scores are not appraiser sign-offs") is False

    def test_has_service_mention_detects_promotional(self):
        assert _has_service_mention("We offer the best appraisal service") is True
        assert _has_service_mention("Hire me for your next appraisal") is True
        assert _has_service_mention("Order an appraisal today") is True

    def test_has_service_mention_rejects_educational(self):
        assert _has_service_mention("Here's how appraisals work") is False
        assert _has_service_mention("Market data shows trends") is False

    def test_has_dollars_or_pct_detects_numbers(self):
        assert _has_dollars_or_pct("Price is $420,000") is True
        assert _has_dollars_or_pct("Down 8% this quarter") is True
        assert _has_dollars_or_pct("No financial data here") is False

    def test_has_specific_data_detects_structured_content(self):
        assert _has_specific_data("Sold 12 units this month in DFW") is True
        assert _has_specific_data("Median price is $375,000") is True
        assert _has_specific_data("Market stayed flat at 2024 levels") is True

    def test_has_specific_data_rejects_vague_text(self):
        assert _has_specific_data("Real estate is interesting") is False

    def test_count_points_counts_bullets_and_numbers(self):
        text = "• Point one\n• Point two\n3. Third item\n- Fourth item"
        assert _count_points(text) == 4

    def test_count_points_returns_zero_for_plain_text(self):
        assert _count_points("Just a plain paragraph with no bullets.") == 0


# ---------------------------------------------------------------------------
# classifier.py - Subreddit / platform recommendations
# ---------------------------------------------------------------------------


class TestRecommendSubreddits:
    """Tests for _recommend_subreddits helper."""

    def test_returns_empty_when_not_safe(self):
        result = _recommend_subreddits(pillar=1, text="Some text", subreddit_safe=False)
        assert result == []

    def test_returns_pillar_default_subs(self):
        result = _recommend_subreddits(pillar=1, text="Some text", subreddit_safe=True)
        assert len(result) >= 1
        assert "r/realestateinvesting" in result

    def test_adds_dfw_subs_when_dallas_mentioned(self):
        # Use pillar 5 which has only 3 default subs, leaving room for DFW additions
        result = _recommend_subreddits(
            pillar=5, text="Looking at properties in Dallas TX", subreddit_safe=True
        )
        assert any("dfw" in s.lower() or "dallas" in s.lower() for s in result)

    def test_respects_cap_at_four(self):
        result = _recommend_subreddits(
            pillar=1,
            text="DFW Dallas Fort Worth Tarrant Collin Denton Frisco McKinney",
            subreddit_safe=True,
        )
        assert len(result) <= 4


class TestRecommendPlatforms:
    """Tests for _recommend_platforms helper."""

    def test_public_feed_safe_adds_linkedin_and_x(self):
        platforms = _recommend_platforms(
            public_feed_safe=True,
            long_form_safe=False,
            subreddit_safe=False,
            promotion_risk_level="low",
        )
        assert "linkedin" in platforms
        assert "x" in platforms

    def test_long_form_adds_newsletter_platforms(self):
        platforms = _recommend_platforms(
            public_feed_safe=True,
            long_form_safe=True,
            subreddit_safe=False,
            promotion_risk_level="low",
        )
        assert "medium" in platforms
        assert "substack" in platforms
        assert "beehiiv" in platforms

    def test_low_risk_adds_reddit_when_safe(self):
        platforms = _recommend_platforms(
            public_feed_safe=True,
            long_form_safe=False,
            subreddit_safe=True,
            promotion_risk_level="low",
        )
        assert "reddit" in platforms

    def test_high_risk_reddit_excluded(self):
        platforms = _recommend_platforms(
            public_feed_safe=True,
            long_form_safe=False,
            subreddit_safe=True,
            promotion_risk_level="high",
        )
        assert "reddit" not in platforms

    def test_no_duplicates(self):
        platforms = _recommend_platforms(
            public_feed_safe=True,
            long_form_safe=True,
            subreddit_safe=True,
            promotion_risk_level="low",
        )
        assert len(platforms) == len(set(platforms))


# ---------------------------------------------------------------------------
# classifier.py - classify() function
# ---------------------------------------------------------------------------


class TestClassify:
    """Tests for the main classify() function."""

    def test_educational_post_low_risk(self):
        result = classify(EDUCATIONAL_POST)
        assert result["promotion_risk_level"] == "low"
        assert result["public_feed_safe"] is True

    def test_promotional_post_high_risk(self):
        result = classify(PROMOTIONAL_POST)
        assert result["promotion_risk_level"] == "high"
        assert result["public_feed_safe"] is False

    def test_educational_post_subreddit_safe(self):
        result = classify(EDUCATIONAL_POST)
        # Educational pillar 1, has data, no CTA, no service mention, low risk
        assert result["subreddit_safe"] is True

    def test_promotional_post_not_subreddit_safe(self):
        result = classify(PROMOTIONAL_POST)
        assert result["subreddit_safe"] is False

    def test_educational_post_long_form_safe(self):
        # Ensure the post has explicit char_count > 800 for reliable testing
        post = {**EDUCATIONAL_POST, "char_count": 900}
        result = classify(post)
        # >800 chars + bullet points
        assert result["long_form_safe"] is True

    def test_short_tip_not_long_form_safe(self):
        result = classify(SHORT_TIP_POST)
        assert result["long_form_safe"] is False

    def test_outreach_snippet_safe_with_dollar_data(self):
        result = classify(EDUCATIONAL_POST)
        assert result["outreach_snippet_safe"] is True

    def test_returns_content_class_with_all_keys(self):
        result = classify(EDUCATIONAL_POST)
        expected_keys = {
            "public_feed_safe",
            "group_safe",
            "subreddit_safe",
            "long_form_safe",
            "short_form_video_safe",
            "outreach_snippet_safe",
            "sms_followup_safe",
            "promotion_risk_level",
            "manual_review_required",
            "recommended_subreddits",
            "recommended_platforms",
        }
        assert set(result.keys()) >= expected_keys

    def test_manual_review_required_for_medium_risk(self):
        post = {**EDUCATIONAL_POST, "format_type": "promo"}
        result = classify(post)
        # promo format → medium risk → manual review required
        assert result["manual_review_required"] is True

    def test_recommended_platforms_not_empty(self):
        result = classify(EDUCATIONAL_POST)
        assert len(result["recommended_platforms"]) > 0

    def test_pillar_subreddits_mapping_has_six_pillars(self):
        assert len(PILLAR_SUBREDDITS) == 6
        for pillar in range(1, 7):
            assert pillar in PILLAR_SUBREDDITS
            assert isinstance(PILLAR_SUBREDDITS[pillar], list)
            assert len(PILLAR_SUBREDDITS[pillar]) > 0


# ---------------------------------------------------------------------------
# queue.py tests
# ---------------------------------------------------------------------------


class TestQueue:
    """Tests for the content queue manager (queue.py)."""

    @pytest.fixture(autouse=True)
    def _redirect_queue_path(self, monkeypatch, tmp_path):
        """Redirect QUEUE_PATH to a temp file so tests don't touch production data."""
        self.tmp_queue = tmp_path / "test_queue.json"
        monkeypatch.setattr(queue_mod, "QUEUE_PATH", self.tmp_queue)
        yield
        # Cleanup
        if self.tmp_queue.exists():
            self.tmp_queue.unlink()

    def test_valid_platforms_constant(self):
        assert "linkedin" in VALID_PLATFORMS
        assert "x_post" in VALID_PLATFORMS
        assert "reddit" in VALID_PLATFORMS
        assert "beehiiv" in VALID_PLATFORMS
        assert len(VALID_PLATFORMS) >= 10

    def test_add_to_queue_returns_item_id(self):
        item_id = add_to_queue(
            post_urn="urn:li:activity:12345",
            platform="x_post",
            content="Test tweet content",
        )
        assert isinstance(item_id, str)
        assert len(item_id) == 12

    def test_add_to_queue_raises_for_invalid_platform(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            add_to_queue(
                post_urn="urn:li:activity:12345",
                platform="nonexistent_platform",
                content="test",
            )

    def test_add_to_queue_review_item_status(self):
        item_id = add_to_queue(
            post_urn="urn:li:activity:12345",
            platform="reddit",
            content="Reddit post draft",
            requires_review=True,
        )
        item = get_item(item_id)
        assert item["status"] == STATUS_REVIEW
        assert item["requires_review"] is True

    def test_get_pending_returns_empty_initially(self):
        items = get_pending()
        assert items == []

    def test_get_pending_after_add(self):
        item_id = add_to_queue(
            post_urn="urn:li:activity:99999",
            platform="linkedin",
            content="LinkedIn group post",
            requires_review=False,
        )
        items = get_pending()
        assert len(items) == 1
        assert items[0]["item_id"] == item_id
        assert items[0]["platform"] == "linkedin"

    def test_get_pending_filtered_by_platform(self):
        add_to_queue(post_urn="urn:li:a:1", platform="x_post", content="x1")
        add_to_queue(post_urn="urn:li:a:2", platform="reddit", content="r1")
        x_items = get_pending(platform="x_post")
        assert len(x_items) == 1
        assert x_items[0]["platform"] == "x_post"

    def test_mark_posted_updates_status(self):
        item_id = add_to_queue(
            post_urn="urn:li:a:1", platform="x_post", content="tweet"
        )
        mark_posted(item_id, {"url": "https://x.com/status/1"})
        item = get_item(item_id)
        assert item["status"] == STATUS_POSTED
        assert item["posted_at"] is not None
        assert item["result"]["url"] == "https://x.com/status/1"

    def test_mark_failed_updates_status(self):
        item_id = add_to_queue(
            post_urn="urn:li:a:1", platform="x_post", content="tweet"
        )
        mark_failed(item_id, "Network error")
        item = get_item(item_id)
        assert item["status"] == STATUS_FAILED
        assert "Network error" in item["result"]["error"]

    def test_mark_skipped_updates_status(self):
        item_id = add_to_queue(
            post_urn="urn:li:a:1", platform="x_post", content="tweet"
        )
        mark_skipped(item_id, "Auto-post disabled")
        item = get_item(item_id)
        assert item["status"] == STATUS_SKIPPED
        assert "Auto-post disabled" in item["result"]["skipped_reason"]

    def test_get_review_queue(self):
        add_to_queue(post_urn="urn:li:a:1", platform="reddit", content="r1", requires_review=True)
        add_to_queue(post_urn="urn:li:a:2", platform="x_post", content="x1", requires_review=False)
        review_items = get_review_queue()
        assert len(review_items) == 1
        assert review_items[0]["platform"] == "reddit"

    def test_get_all_filtered_by_status(self):
        id1 = add_to_queue(post_urn="urn:li:a:1", platform="x_post", content="x1")
        mark_posted(id1, {"url": "ok"})
        posted = get_all(status=STATUS_POSTED)
        assert len(posted) == 1
        assert posted[0]["item_id"] == id1

    def test_get_item_raises_keyerror_for_missing(self):
        with pytest.raises(KeyError, match="not found"):
            get_item("nonexistent-id")

    def test_get_stats_returns_structure(self):
        add_to_queue(post_urn="urn:li:a:1", platform="x_post", content="x1")
        add_to_queue(post_urn="urn:li:a:2", platform="reddit", content="r1", requires_review=True)
        stats = get_stats()
        assert "status_counts" in stats
        assert "platform_counts" in stats
        assert stats["status_counts"]["total"] == 2
        assert stats["status_counts"]["pending"] == 1
        assert stats["status_counts"]["review_required"] == 1

    def test_add_to_queue_stores_metadata(self):
        item_id = add_to_queue(
            post_urn="urn:li:a:1",
            platform="beehiiv",
            content="newsletter",
            metadata={"pillar": 3, "status": "draft"},
        )
        item = get_item(item_id)
        assert item["metadata"]["pillar"] == 3
        assert item["metadata"]["status"] == "draft"

    def test_clear_posted_removes_old_entries(self):
        """clear_posted removes POSTED items older than N days."""
        id1 = add_to_queue(post_urn="urn:li:a:1", platform="x_post", content="x1")
        mark_posted(id1, {"url": "ok"})
        # Manually backdate the posted_at timestamp
        queue = queue_mod._load_queue()
        for item in queue["items"]:
            if item["item_id"] == id1:
                item["posted_at"] = "2020-01-01T00:00:00Z"
        queue_mod._save_queue(queue)

        removed = clear_posted(older_than_days=30)
        assert removed >= 1

    def test_mark_posted_raises_for_unknown_id(self):
        with pytest.raises(KeyError, match="not found"):
            mark_posted("nonexistent-id", {"url": "ok"})
