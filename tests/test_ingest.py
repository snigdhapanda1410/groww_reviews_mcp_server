"""
tests/test_ingest.py
─────────────────────────────────────────────────────────────────────────────
Phase 6 — Unit tests for src/ingest.py

Coverage:
  D1.4   No PII fields in output (userName, userImage, reviewId, …)
  D1.5   Public fetch only (no login code paths)
  EC-01  Zero reviews → IngestError
  EC-02  < 3 reviews → window widening; still < 3 → IngestError
  EC-03  Scraper network error → exponential backoff retry
  EC-05  Empty / whitespace-only content → filtered
  EC-06  Duplicate reviews → deduplicated
  EC-07  PII in content (email, phone, Aadhaar) → [REDACTED]
  EC-08  Null / malformed / future date → handled gracefully
  EC-09  Content > MAX_CONTENT_CHARS → truncated
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.ingest import (
    IngestError,
    MAX_CONTENT_CHARS,
    fetch_reviews,
    load_reviews_from_snapshot,
    redact_pii,
    remove_emojis,
    is_english,
    has_non_latin_script,
    _dedup,
    _in_window,
    _parse_date,
    _sanitise_one,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    """Write a minimal config.yaml into a temp directory."""
    cfg = {
        "review": {
            "app_id": "com.nextbillion.groww",
            "country": "in",
            "language": "en",
            "weeks_back": 10,
            "max_reviews": 50,
        },
        "output": {
            "data_dir": str(tmp_path / "data"),
            "log_level": "DEBUG",
        },
    }
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(cfg))
    return cfg_file


def _make_raw_review(
    content: str = "Great app, love using it for all my investments and trading!",
    score: int = 4,
    days_ago: int = 5,
    user_name: str = "TestUser",
    review_id: str = "abc123",
    version: str = "5.0.0",
) -> dict:
    """Build a fake raw scraper response dict with PII fields present."""
    return {
        "userName": user_name,
        "userImage": "https://example.com/img.jpg",
        "content": content,
        "score": score,
        "thumbsUpCount": 3,
        "reviewCreatedVersion": version,
        "at": datetime.now(tz=timezone.utc) - timedelta(days=days_ago),
        "replyContent": None,
        "repliedAt": None,
        "reviewId": review_id,
    }


def _make_sanitised(
    content: str = "Great app, love using it for all my investments and trading!",
    score: int = 4,
    days_ago: int = 5,
) -> dict:
    """Build an already-sanitised review dict (no PII keys)."""
    date = (datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%d"
    )
    return {"score": score, "content": content, "date": date, "version": "5.0.0"}


# ─── redact_pii ────────────────────────────────────────────────────────────────


class TestRedactPii:
    def test_email_redacted(self):
        text = "Contact me at john.doe@example.com for help"
        result, count = redact_pii(text)
        assert "[REDACTED]" in result
        assert "john.doe@example.com" not in result
        assert count == 1

    def test_indian_phone_redacted(self):
        text = "Call me on 9876543210 anytime"
        result, count = redact_pii(text)
        assert "[REDACTED]" in result
        assert "9876543210" not in result
        assert count == 1

    def test_phone_with_country_code_redacted(self):
        text = "Reach me at +91 9876543210"
        result, count = redact_pii(text)
        assert "[REDACTED]" in result
        assert count == 1

    def test_aadhaar_redacted(self):
        text = "My Aadhaar is 1234 5678 9012"
        result, count = redact_pii(text)
        assert "[REDACTED]" in result
        assert "1234 5678 9012" not in result
        assert count == 1

    def test_multiple_pii_redacted(self):
        text = "Email john@test.com or call 9876543210"
        result, count = redact_pii(text)
        assert count == 2
        assert "john@test.com" not in result
        assert "9876543210" not in result

    def test_clean_text_unchanged(self):
        text = "The KYC process is broken, please fix it."
        result, count = redact_pii(text)
        assert result == text
        assert count == 0

    def test_returns_tuple(self):
        result = redact_pii("hello")
        assert isinstance(result, tuple)
        assert len(result) == 2


# ─── _sanitise_one ─────────────────────────────────────────────────────────────


class TestSanitiseOne:
    def test_pii_fields_dropped(self):
        """D1.4 — PII field keys must not appear in output."""
        raw = _make_raw_review()
        result = _sanitise_one(raw)
        assert result is not None
        pii_keys = {"userName", "userImage", "reviewId", "replyContent",
                    "repliedAt", "thumbsUpCount"}
        assert pii_keys.isdisjoint(result.keys()), (
            f"PII keys found in output: {pii_keys & result.keys()}"
        )

    def test_output_schema(self):
        """Output must have exactly score, content, date, version."""
        raw = _make_raw_review()
        result = _sanitise_one(raw)
        assert result is not None
        assert set(result.keys()) == {"score", "content", "date", "version"}

    def test_empty_content_returns_none(self):
        """EC-05 — Empty content filtered out."""
        raw = _make_raw_review(content="")
        assert _sanitise_one(raw) is None

    def test_whitespace_only_content_returns_none(self):
        """EC-05 — Whitespace-only content filtered out."""
        raw = _make_raw_review(content="   ")
        assert _sanitise_one(raw) is None

    def test_short_content_returns_none(self):
        """EC-05 — Content < 10 chars filtered out."""
        raw = _make_raw_review(content="ok")
        assert _sanitise_one(raw) is None

    def test_long_content_truncated(self):
        """EC-09 — Content > MAX_CONTENT_CHARS is truncated."""
        long_text = ("The application investment and trading platform is " * 20)[:MAX_CONTENT_CHARS + 100]
        raw = _make_raw_review(content=long_text)
        result = _sanitise_one(raw)
        assert result is not None
        assert len(result["content"]) <= MAX_CONTENT_CHARS + 1  # +1 for ellipsis char
        assert result["content"].endswith("…")

    def test_email_in_content_redacted(self):
        """EC-07 — Email addresses in content replaced."""
        raw = _make_raw_review(content="Please contact me at user@gmail.com to get my refund processed quickly")
        result = _sanitise_one(raw)
        assert result is not None
        assert "user@gmail.com" not in result["content"]
        assert "[REDACTED]" in result["content"]

    def test_phone_in_content_redacted(self):
        """EC-07 — Indian phone numbers in content replaced."""
        raw = _make_raw_review(content="Please call 9123456789 to resolve my account issue as soon as possible")
        result = _sanitise_one(raw)
        assert result is not None
        assert "9123456789" not in result["content"]
        assert "[REDACTED]" in result["content"]

    def test_null_date_kept_as_unknown(self):
        """EC-08 — None date becomes 'unknown', review kept."""
        raw = _make_raw_review()
        raw["at"] = None
        result = _sanitise_one(raw)
        assert result is not None
        assert result["date"] == "unknown"

    def test_datetime_date_parsed_correctly(self):
        raw = _make_raw_review(days_ago=7)
        result = _sanitise_one(raw)
        assert result is not None
        # Date should be a valid YYYY-MM-DD
        datetime.strptime(result["date"], "%Y-%m-%d")

    def test_score_preserved(self):
        raw = _make_raw_review(score=2)
        result = _sanitise_one(raw)
        assert result is not None
        assert result["score"] == 2

    def test_version_preserved(self):
        raw = _make_raw_review(version="6.1.0")
        result = _sanitise_one(raw)
        assert result is not None
        assert result["version"] == "6.1.0"


# ─── remove_emojis ─────────────────────────────────────────────────────────────


class TestRemoveEmojis:
    def test_strip_common_emojis(self):
        text = "very nice 👍 and great app 💯 with excellent features 🚀"
        cleaned = remove_emojis(text)
        assert cleaned == "very nice and great app with excellent features"

    def test_strip_symbols_and_stars(self):
        text = "Loved it! ❤️ 5 ⭐ rating!"
        cleaned = remove_emojis(text)
        assert cleaned == "Loved it! 5 rating!"

    def test_text_without_emojis_unchanged(self):
        text = "Simple plain English text without any symbols."
        assert remove_emojis(text) == text

    def test_whitespace_collapsed_after_emoji_removal(self):
        text = "Awesome 👍 👍 👍 app"
        cleaned = remove_emojis(text)
        assert cleaned == "Awesome app"


# ─── is_english / Language Filtering ──────────────────────────────────────────


class TestLanguageFiltering:
    def test_english_review_accepted(self):
        text = "Charts are not opening even in a good network. It is showing failed to load."
        assert is_english(text) is True

    def test_devanagari_hindi_rejected(self):
        text = "बहुत बढ़िया है ये aap ek bar ट्राय kr sakte hai"
        assert is_english(text) is False
        assert has_non_latin_script(text) is True

    def test_hinglish_review_rejected(self):
        text = "ekdm bekar apk hai bilkul bhi thik nahi or koi ipo hit nahi krta hai"
        assert is_english(text) is False

    def test_hinglish_money_rejection(self):
        text = "2 baje se pehle withdrawal nahi honge aur 2 bje baad me withdraw kroge toh kal tak honge"
        assert is_english(text) is False

    def test_marathi_review_rejected(self):
        text = "khup chaan app ahhe Grow. UI pan mast ahhe"
        assert is_english(text) is False


# ─── Word Count Filtering (> 8 words) ──────────────────────────────────────────


class TestWordCountFiltering:
    def test_review_with_8_words_dropped(self):
        # Exactly 8 words -> should be dropped (must be strictly > 8 words)
        raw = _make_raw_review(content="One two three four five six seven eight.")
        assert _sanitise_one(raw, min_words=8) is None

    def test_review_with_fewer_than_8_words_dropped(self):
        raw = _make_raw_review(content="Very good app, nice trading experience.")
        assert _sanitise_one(raw, min_words=8) is None

    def test_review_with_more_than_8_words_kept(self):
        # 10 words -> kept
        raw = _make_raw_review(content="One two three four five six seven eight nine words.")
        result = _sanitise_one(raw, min_words=8)
        assert result is not None
        assert "One two three" in result["content"]

    def test_emoji_stripped_before_word_counting(self):
        # 2 words + emojis -> dropped
        raw = _make_raw_review(content="Good app 👍 💯 🚀 ❤️ ⭐")
        assert _sanitise_one(raw, min_words=8, strip_emojis=True) is None

    def test_hindi_review_dropped_in_sanitise(self):
        raw = _make_raw_review(content="abhi groww aap me bahut kuch new update karna baki he ....ok")
        assert _sanitise_one(raw, english_only=True) is None


# ─── _in_window ────────────────────────────────────────────────────────────────


class TestInWindow:
    def _cutoff(self, weeks: int = 10) -> datetime:
        return datetime.now(tz=timezone.utc) - timedelta(weeks=weeks)

    def test_recent_review_included(self):
        r = _make_sanitised(days_ago=5)
        assert _in_window(r, self._cutoff()) is True

    def test_old_review_excluded(self):
        r = _make_sanitised(days_ago=365)
        assert _in_window(r, self._cutoff()) is False

    def test_unknown_date_included(self):
        """EC-08 — Unknown-date reviews kept."""
        r = {"score": 3, "content": "test", "date": "unknown", "version": "1.0"}
        assert _in_window(r, self._cutoff()) is True

    def test_future_date_excluded(self):
        """EC-08 — Future-dated reviews dropped."""
        future = (datetime.now(tz=timezone.utc) + timedelta(days=5)).strftime(
            "%Y-%m-%d"
        )
        r = {"score": 3, "content": "test", "date": future, "version": "1.0"}
        assert _in_window(r, self._cutoff()) is False


# ─── _dedup ────────────────────────────────────────────────────────────────────


class TestDedup:
    def test_identical_reviews_deduplicated(self):
        """EC-06 — Exact duplicate removed."""
        r = _make_sanitised("Same review text here!!", days_ago=3)
        result = _dedup([r, r])
        assert len(result) == 1

    def test_different_reviews_kept(self):
        a = _make_sanitised("Review A content text", days_ago=3)
        b = _make_sanitised("Review B content text", days_ago=4)
        result = _dedup([a, b])
        assert len(result) == 2

    def test_empty_list(self):
        assert _dedup([]) == []

    def test_order_preserved(self):
        a = _make_sanitised("First review text here", days_ago=1)
        b = _make_sanitised("Second review text here", days_ago=2)
        result = _dedup([a, b])
        assert result[0]["content"] == a["content"]


# ─── fetch_reviews (integration with mocked scraper) ──────────────────────────


class TestFetchReviews:
    """
    All tests mock google_play_scraper.reviews to avoid real network calls.
    """

    def _raw_batch(self, n: int = 20, days_ago: int = 5) -> list[dict]:
        return [_make_raw_review(
            content=f"Review number {i}: KYC is broken and the app crashes a lot.",
            days_ago=days_ago,
        ) for i in range(n)]

    def test_happy_path_returns_reviews(self, config_file, tmp_path):
        """Basic: mocked scraper returns reviews → function succeeds."""
        with patch("src.ingest.gps_reviews", return_value=(self._raw_batch(20), None)):
            result = fetch_reviews(config_path=str(config_file))
        assert len(result) > 0

    def test_output_has_no_pii_keys(self, config_file):
        """D1.4 — PII keys must be absent from returned reviews."""
        with patch("src.ingest.gps_reviews", return_value=(self._raw_batch(20), None)):
            result = fetch_reviews(config_path=str(config_file))
        pii_keys = {"userName", "userImage", "reviewId", "replyContent",
                    "repliedAt", "thumbsUpCount"}
        for review in result:
            assert pii_keys.isdisjoint(review.keys()), (
                f"PII keys found: {pii_keys & review.keys()}"
            )

    def test_output_schema_correct(self, config_file):
        """Each review must have exactly score, content, date, version."""
        with patch("src.ingest.gps_reviews", return_value=(self._raw_batch(10), None)):
            result = fetch_reviews(config_path=str(config_file))
        for review in result:
            assert set(review.keys()) == {"score", "content", "date", "version"}

    def test_date_filter_applied(self, config_file):
        """D1.2 — Reviews outside weeks_back window must be excluded."""
        old_reviews = self._raw_batch(10, days_ago=365)  # well outside 10-week window
        recent_reviews = self._raw_batch(10, days_ago=5)
        with patch("src.ingest.gps_reviews",
                   return_value=(old_reviews + recent_reviews, None)):
            result = fetch_reviews(config_path=str(config_file))
        # Old reviews (365 days ago) should be filtered; recent ones kept
        for r in result:
            if r["date"] != "unknown":
                date = datetime.strptime(r["date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                cutoff = datetime.now(tz=timezone.utc) - timedelta(weeks=10)
                assert date >= cutoff, f"Old review leaked through: {r['date']}"

    def test_json_snapshot_saved(self, config_file, tmp_path):
        """JSON snapshot must be saved to data/ directory."""
        with patch("src.ingest.gps_reviews", return_value=(self._raw_batch(10), None)):
            fetch_reviews(config_path=str(config_file), week_ending="2026-11-01")
        snapshot = tmp_path / "data" / "reviews_2026-11-01.json"
        assert snapshot.exists(), "Snapshot file not found"

    def test_snapshot_schema(self, config_file, tmp_path):
        """Saved JSON must have fetched_at, app_id, week_ending, review_count, reviews."""
        with patch("src.ingest.gps_reviews", return_value=(self._raw_batch(10), None)):
            fetch_reviews(config_path=str(config_file), week_ending="2026-11-01")
        snapshot = tmp_path / "data" / "reviews_2026-11-01.json"
        with snapshot.open() as f:
            data = json.load(f)
        for key in ("fetched_at", "app_id", "week_ending", "review_count", "reviews"):
            assert key in data, f"Missing key in snapshot: {key}"
        assert data["app_id"] == "com.nextbillion.groww"

    def test_snapshot_has_no_pii_keys(self, config_file, tmp_path):
        """Saved JSON reviews must not contain PII keys (D1.4)."""
        with patch("src.ingest.gps_reviews", return_value=(self._raw_batch(10), None)):
            fetch_reviews(config_path=str(config_file), week_ending="2026-11-01")
        snapshot = tmp_path / "data" / "reviews_2026-11-01.json"
        with snapshot.open() as f:
            data = json.load(f)
        pii_keys = {"userName", "userImage", "reviewId"}
        for review in data["reviews"]:
            assert pii_keys.isdisjoint(review.keys())

    def test_zero_reviews_raises_ingest_error(self, config_file):
        """EC-01 — Empty scraper result raises IngestError."""
        with patch("src.ingest.gps_reviews", return_value=([], None)):
            with pytest.raises(IngestError, match="No reviews fetched"):
                fetch_reviews(config_path=str(config_file))

    def test_fewer_than_3_reviews_widens_window(self, config_file):
        """EC-02 — < 3 reviews triggers window widening (second scraper call)."""
        two_reviews = self._raw_batch(2)
        enough_reviews = self._raw_batch(10)
        call_count = {"n": 0}

        def fake_scraper(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return two_reviews, None
            return enough_reviews, None

        with patch("src.ingest.gps_reviews", side_effect=fake_scraper):
            result = fetch_reviews(config_path=str(config_file))
        assert call_count["n"] == 2, "Expected two scraper calls (window widening)"
        assert len(result) >= 3

    def test_fewer_than_3_after_widening_raises_error(self, config_file):
        """EC-02 — Still < 3 after widening raises IngestError."""
        one_review = self._raw_batch(1)
        with patch("src.ingest.gps_reviews", return_value=(one_review, None)):
            with pytest.raises(IngestError, match="Insufficient reviews"):
                fetch_reviews(config_path=str(config_file))

    def test_scraper_network_error_retries(self, config_file):
        """EC-03 — Transient errors trigger exponential-backoff retries."""
        good_batch = self._raw_batch(10)
        call_count = {"n": 0}

        def flaky_scraper(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("Simulated timeout")
            return good_batch, None

        with patch("src.ingest.gps_reviews", side_effect=flaky_scraper):
            with patch("src.ingest.time.sleep"):  # skip actual sleep in tests
                result = fetch_reviews(config_path=str(config_file))
        assert call_count["n"] == 3
        assert len(result) > 0

    def test_all_retries_exhausted_raises_error(self, config_file):
        """EC-03 — All retries fail → IngestError."""
        with patch("src.ingest.gps_reviews", side_effect=ConnectionError("timeout")):
            with patch("src.ingest.time.sleep"):
                with pytest.raises(IngestError, match="Play Store fetch failed"):
                    fetch_reviews(config_path=str(config_file))

    def test_data_dir_auto_created(self, config_file, tmp_path):
        """EC-33 — data/ directory created if missing."""
        data_dir = tmp_path / "data"
        assert not data_dir.exists()
        with patch("src.ingest.gps_reviews", return_value=(self._raw_batch(10), None)):
            fetch_reviews(config_path=str(config_file))
        assert data_dir.exists()

    def test_pii_in_content_redacted_in_snapshot(self, config_file, tmp_path):
        """EC-07 — Email + phone redacted before saving to snapshot."""
        dirty_reviews = [
            _make_raw_review(
                content=f"Review {i}: Call me at 9876543210 or email abc@test.com to resolve KYC issue",
                days_ago=i + 1,
            )
            for i in range(5)
        ]
        with patch("src.ingest.gps_reviews", return_value=(dirty_reviews, None)):
            fetch_reviews(config_path=str(config_file), week_ending="2026-11-01")
        snapshot = tmp_path / "data" / "reviews_2026-11-01.json"
        raw_text = snapshot.read_text()
        assert "9876543210" not in raw_text, "Phone number leaked into snapshot"
        assert "abc@test.com" not in raw_text, "Email leaked into snapshot"
        assert "[REDACTED]" in raw_text


# ─── load_reviews_from_snapshot ────────────────────────────────────────────────


class TestLoadReviewsFromSnapshot:
    def test_loads_correctly(self, tmp_path):
        reviews = [{"score": 4, "content": "Good app", "date": "2026-10-01",
                    "version": "5.0"}]
        snapshot = {
            "fetched_at": "2026-11-01T10:00:00",
            "app_id": "com.nextbillion.groww",
            "week_ending": "2026-11-01",
            "review_count": 1,
            "reviews": reviews,
        }
        path = tmp_path / "reviews_2026-11-01.json"
        path.write_text(json.dumps(snapshot))
        result = load_reviews_from_snapshot(path)
        assert len(result) == 1
        assert result[0]["content"] == "Good app"


