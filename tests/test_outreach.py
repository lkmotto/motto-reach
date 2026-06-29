"""
Tests for motto-reach outreach/ package.

Covers abcd.py (Thompson Sampling), reddit_client._score,
x_client.daily_x_limit, observability._basic_auth_header,
reporter.build_email_body, and ollama_client constants.
"""
import sys
import json
import binascii
from pathlib import Path

import pytest

# Ensure outreach/ is on sys.path so outreach modules can be imported
_OUTREACH_DIR = Path(__file__).parent.parent / "outreach"
if str(_OUTREACH_DIR) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_DIR))

# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


class TestImports:
    """Verify outreach modules are importable (without triggering side effects)."""

    def test_abcd_module_imports(self):
        import abcd  # noqa: F401
        assert abcd.VARIANTS is not None

    def test_observability_module_imports(self):
        from observability import _basic_auth_header  # noqa: F401
        assert callable(_basic_auth_header)

    def test_reporter_module_imports(self):
        from reporter import build_email_body  # noqa: F401
        assert callable(build_email_body)

    def test_ollama_client_imports(self):
        from ollama_client import LUKE_SYSTEM, MODELS  # noqa: F401
        assert isinstance(LUKE_SYSTEM, str)
        assert len(LUKE_SYSTEM) > 100
        assert isinstance(MODELS, list)

    def test_reddit_client_score_imports(self):
        from reddit_client import _score  # noqa: F401
        assert callable(_score)

    def test_x_client_daily_limit_imports(self):
        from x_client import daily_x_limit  # noqa: F401
        assert callable(daily_x_limit)


# ---------------------------------------------------------------------------
# abcd.py - Thompson Sampling ABCD variant tracker
# ---------------------------------------------------------------------------


class TestABCDVariants:
    """Tests for ABCD variant definitions and sampling."""

    def test_variants_has_four_entries(self):
        from abcd import VARIANTS
        assert len(VARIANTS) == 4
        for expected_key in ("A", "B", "C", "D"):
            assert expected_key in VARIANTS

    def test_each_variant_has_required_fields(self):
        from abcd import VARIANTS
        for v_id, v in VARIANTS.items():
            assert "name" in v, f"Variant {v_id} missing 'name'"
            assert "description" in v, f"Variant {v_id} missing 'description'"
            assert "hypothesis" in v, f"Variant {v_id} missing 'hypothesis'"

    def test_sample_variant_returns_valid_key(self, monkeypatch, tmp_path):
        from abcd import sample_variant, STATE_FILE
        # Redirect state file to tmp
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr("abcd.STATE_FILE", tmp_state)

        # Run many samples to ensure all variants can be selected
        results = {sample_variant("dm") for _ in range(200)}
        for v in ("A", "B", "C", "D"):
            assert v in results, f"Variant {v} was never sampled in 200 draws"

    def test_sample_variant_defaults_to_dm_channel(self, monkeypatch, tmp_path):
        from abcd import sample_variant, STATE_FILE
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr("abcd.STATE_FILE", tmp_state)

        result = sample_variant()  # no channel specified
        assert result in ("A", "B", "C", "D")

    def test_record_send_and_reply_increases_counts(self, monkeypatch, tmp_path):
        import abcd
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr(abcd, "STATE_FILE", tmp_state)

        abcd.record_send("A", "dm")
        abcd.record_reply("A", "dm", positive=True)

        status = abcd.get_status("dm")
        assert status["variants"]["A"]["sends"] == 1
        assert status["variants"]["A"]["replies"] == 1

    def test_get_status_returns_experiment_metadata(self, monkeypatch, tmp_path):
        import abcd
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr(abcd, "STATE_FILE", tmp_state)

        status = abcd.get_status("dm")
        assert "variants" in status
        assert "leader" in status
        assert "leader_p_best" in status
        assert "total_sends" in status
        assert "days_running" in status

    def test_sends_after_replies_affects_p_best(self, monkeypatch, tmp_path):
        import abcd
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr(abcd, "STATE_FILE", tmp_state)

        # Give variant B many positive replies
        for _ in range(20):
            abcd.record_send("B", "dm")
            abcd.record_reply("B", "dm", positive=True)
        # Give variant A only failures
        for _ in range(20):
            abcd.record_send("A", "dm")
            abcd.record_reply("A", "dm", positive=False)

        status = abcd.get_status("dm")
        # B should have higher p_best than A after many successes
        assert status["variants"]["B"]["p_best"] > status["variants"]["A"]["p_best"]

    def test_format_report_includes_leader_tag(self, monkeypatch, tmp_path):
        import abcd
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr(abcd, "STATE_FILE", tmp_state)

        report = abcd.format_report("dm")
        assert "ABCD EXPERIMENT" in report
        assert "days running" in report
        assert "Variant A" in report
        assert "Variant D" in report

    def test_empty_channel_returns_empty_status(self, monkeypatch, tmp_path):
        import abcd
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr(abcd, "STATE_FILE", tmp_state)

        status = abcd.get_status("nonexistent_channel")
        assert status == {}

    def test_format_report_empty_channel(self, monkeypatch, tmp_path):
        import abcd
        tmp_state = tmp_path / "abcd_state.json"
        monkeypatch.setattr(abcd, "STATE_FILE", tmp_state)

        report = abcd.format_report("nonexistent_channel")
        assert report == "No experiment data yet."


# ---------------------------------------------------------------------------
# reddit_client.py - _score function
# ---------------------------------------------------------------------------


class TestRedditScore:
    """Tests for the Reddit post scoring function."""

    def test_high_intent_scores_high(self):
        from reddit_client import _score
        title = "Need an appraiser in DFW for DSCR loan"
        body = "Looking for someone who can do a rental income appraisal"
        sc, intent_hits, geo_hits = _score(title, body)
        assert sc >= 30, f"Expected score >= 30, got {sc}"
        assert len(intent_hits) >= 2
        assert len(geo_hits) >= 1

    def test_question_mark_adds_points(self):
        from reddit_client import _score
        sc_with_q, _, _ = _score("Need an appraiser?")
        sc_no_q, _, _ = _score("Need an appraiser")
        assert sc_with_q > sc_no_q

    def test_help_keyword_adds_points(self):
        from reddit_client import _score
        sc_help, _, _ = _score("Help finding appraiser")
        sc_neutral, _, _ = _score("Appraiser information")
        assert sc_help > sc_neutral

    def test_irrelevant_post_scores_low(self):
        from reddit_client import _score
        sc, intent_hits, _ = _score("What's your favorite color?")
        assert sc < 16
        assert intent_hits == []

    def test_dfw_geo_detection(self):
        from reddit_client import _score
        _, _, geo_hits = _score("", "Looking in Dallas Fort Worth area")
        assert len(geo_hits) >= 1

    def test_no_dfw_geo_for_other_cities(self):
        from reddit_client import _score
        _, _, geo_hits = _score("Looking in Austin TX")
        assert geo_hits == []


# ---------------------------------------------------------------------------
# x_client.py - daily_x_limit function
# ---------------------------------------------------------------------------


class TestXDailyLimit:
    """Tests for X/Twitter daily reply limit ramp."""

    def test_day_one_returns_eight(self):
        from x_client import daily_x_limit
        assert daily_x_limit(1) == 8
        assert daily_x_limit(3) == 8

    def test_day_five_returns_fifteen(self):
        from x_client import daily_x_limit
        assert daily_x_limit(5) == 15
        assert daily_x_limit(7) == 15

    def test_day_ten_returns_twenty(self):
        from x_client import daily_x_limit
        assert daily_x_limit(10) == 20
        assert daily_x_limit(14) == 20

    def test_day_fifteen_returns_twentyfive(self):
        from x_client import daily_x_limit
        assert daily_x_limit(15) == 25
        assert daily_x_limit(100) == 25

    def test_zero_days_defaults_to_eight(self):
        from x_client import daily_x_limit
        assert daily_x_limit(0) == 8


# ---------------------------------------------------------------------------
# observability.py - _basic_auth_header function
# ---------------------------------------------------------------------------


class TestBasicAuthHeader:
    """Tests for the Basic auth header builder."""

    def test_encodes_username_password(self):
        from observability import _basic_auth_header
        result = _basic_auth_header("user", "pass")
        assert result.startswith("Basic ")
        # Decode and verify
        encoded_part = result.split(" ", 1)[1]
        decoded = binascii.a2b_base64(encoded_part).decode("ascii")
        assert decoded == "user:pass"

    def test_special_characters_encoded(self):
        from observability import _basic_auth_header
        result = _basic_auth_header("pk-abc123", "sk-xyz789!")
        assert result.startswith("Basic ")
        encoded_part = result.split(" ", 1)[1]
        decoded = binascii.a2b_base64(encoded_part).decode("ascii")
        assert decoded == "pk-abc123:sk-xyz789!"

    def test_empty_credentials(self):
        from observability import _basic_auth_header
        result = _basic_auth_header("", "")
        assert result == "Basic Og=="  # base64 of ":"


# ---------------------------------------------------------------------------
# reporter.py - build_email_body function
# ---------------------------------------------------------------------------


class TestReporterBuildEmail:
    """Tests for the email digest body builder."""

    def test_empty_summary_produces_report(self):
        from reporter import build_email_body
        summary = {"sent": [], "account_health": {}}
        body = build_email_body(summary, {}, [], "")
        assert "OUTREACH SUMMARY" in body
        assert "SENT THIS CYCLE" in body
        assert "None this cycle" in body

    def test_with_sent_items_includes_targets(self):
        from reporter import build_email_body
        summary = {
            "sent": [
                {
                    "type": "reddit_dm",
                    "author": "testuser",
                    "subreddit": "realestateinvesting",
                    "title": "Need an appraiser",
                    "variant": "B",
                    "dm_sent": True,
                    "comment_sent": False,
                }
            ],
            "account_health": {"reddit_dms_today": 1, "reddit_dm_limit": 5, "reddit_status": "active"},
        }
        body = build_email_body(summary, {}, [], "")
        assert "testuser" in body
        assert "realestateinvesting" in body

    def test_with_abcd_status_includes_leader(self):
        from reporter import build_email_body
        abcd_status = {
            "variants": {
                "A": {"name": "Direct", "sends": 10, "reply_rate": 5.0, "p_best": 30.0},
                "B": {"name": "Data-led", "sends": 10, "reply_rate": 15.0, "p_best": 70.0},
            },
            "leader": "B",
            "days_running": 5,
        }
        body = build_email_body({"sent": [], "account_health": {}}, abcd_status, [], "")
        assert "ABCD EXPERIMENT" in body
        assert "LEADING" in body

    def test_with_inbox_replies_shows_replies(self):
        from reporter import build_email_body
        replies = [{"author": "helpful_user", "body": "Thanks for the info!"}]
        body = build_email_body({"sent": [], "account_health": {}}, {}, replies, "")
        assert "helpful_user" in body
        assert "Thanks for the info!" in body

    def test_sharpener_note_appears_when_provided(self):
        from reporter import build_email_body
        body = build_email_body(
            {"sent": [], "account_health": {}},
            {},
            [],
            "Try leading with DFW-specific data points.",
        )
        assert "SHARPENER NOTE" in body
        assert "DFW-specific data points" in body


# ---------------------------------------------------------------------------
# ollama_client.py - constants
# ---------------------------------------------------------------------------


class TestOllamaClientConstants:
    """Tests for Ollama client configuration constants."""

    def test_luke_system_is_non_empty(self):
        from ollama_client import LUKE_SYSTEM
        assert isinstance(LUKE_SYSTEM, str)
        assert len(LUKE_SYSTEM) > 200

    def test_luke_system_contains_voice_guidelines(self):
        from ollama_client import LUKE_SYSTEM
        assert "Luke Motto" in LUKE_SYSTEM
        assert "appraiser" in LUKE_SYSTEM.lower()

    def test_models_list_is_non_empty(self):
        from ollama_client import MODELS
        assert isinstance(MODELS, list)
        assert len(MODELS) >= 1
        assert "luke-motto" in MODELS
