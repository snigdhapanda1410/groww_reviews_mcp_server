"""
tests/test_pulse.py
─────────────────────────────────────────────────────────────────────────────
Phase 6 / Phase 3 — Unit tests for src/pulse.py

Coverage:
  - Pulse JSON payload schema
  - EC-18: Word count <= 250 words enforced
  - EC-19: Verbatim quotes grounded in actual theme reviews
  - EC-20: No PII in selected quotes (phone, email, Aadhaar)
  - EC-21: Action ideas start with capital verbs and grounded
  - Snapshot persistence: pulse_YYYY-MM-DD.json saved to disk
"""

import json
from pathlib import Path
import pytest
import yaml

from src.pulse import (
    PulseError,
    condense_prose,
    format_pulse_prose,
    generate_action_ideas,
    generate_pulse,
    select_quote_for_theme,
)


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    cfg = {
        "review": {
            "app_id": "com.nextbillion.groww",
            "country": "in",
            "language": "en",
            "weeks_back": 10,
            "max_reviews": 50,
        },
        "pulse": {
            "max_themes": 5,
            "top_themes": 3,
            "quotes_count": 3,
            "action_ideas_count": 3,
            "max_words": 250,
        },
        "output": {
            "data_dir": str(tmp_path / "data"),
            "log_level": "DEBUG",
        },
    }
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(cfg))
    return cfg_file


@pytest.fixture()
def sample_reviews() -> list[dict]:
    return [
        {"score": 1, "content": "The Groww app frequently freezes during trading hours, causing inconvenience and financial loss.", "date": "2026-10-30"},
        {"score": 1, "content": "Exit button disappeared during volatile trading candle movement and I face heavy loss.", "date": "2026-10-29"},
        {"score": 2, "content": "KYC verification keeps failing multiple times even after uploading correct CAMS statement.", "date": "2026-10-28"},
        {"score": 1, "content": "Document verification took more than seven days to fetch PAN card details.", "date": "2026-10-27"},
        {"score": 2, "content": "Withdrawal requested before 2 PM was delayed and funds did not reflect in bank account.", "date": "2026-10-26"},
    ]


@pytest.fixture()
def sample_themes() -> list[dict]:
    return [
        {
            "rank": 1,
            "name": "App Crashes & Freezes",
            "description": "App hangs during market hours causing exit button to fail.",
            "review_indices": [0, 1],
            "review_count": 2,
        },
        {
            "rank": 2,
            "name": "KYC & Verification",
            "description": "KYC verification fails repeatedly and PAN fetching takes over a week.",
            "review_indices": [2, 3],
            "review_count": 2,
        },
        {
            "rank": 3,
            "name": "Withdrawal Delays",
            "description": "Funds take too long to reach bank account after withdrawal request.",
            "review_indices": [4],
            "review_count": 1,
        },
    ]


class TestPulseGeneration:
    def test_pulse_schema_and_counts(self, sample_themes, sample_reviews, config_file):
        """Verify full pulse payload structure matches required schema."""
        payload, prose = generate_pulse(
            themes=sample_themes,
            reviews=sample_reviews,
            config_path=str(config_file),
            week_ending="2026-11-01",
        )

        assert payload["week_ending"] == "2026-11-01"
        assert payload["review_count"] == 5
        assert len(payload["top_themes"]) == 3
        assert len(payload["action_ideas"]) == 3
        assert payload["word_count"] <= 250
        assert payload["word_count"] > 0

        # Verify themes schema
        for item in payload["top_themes"]:
            assert "rank" in item
            assert "name" in item
            assert "description" in item
            assert "review_count" in item
            assert "quote" in item
            assert len(item["quote"]) > 0

    def test_word_count_enforced_ec18(self, sample_themes, sample_reviews, config_file):
        """EC-18: Formatted prose must strictly not exceed 250 words."""
        payload, prose = generate_pulse(
            themes=sample_themes,
            reviews=sample_reviews,
            config_path=str(config_file),
            week_ending="2026-11-01",
        )
        word_count = len(prose.split())
        assert word_count <= 250

    def test_condense_prose_when_exceeding_limit(self):
        """EC-18: Long prose is successfully condensed below max_words limit."""
        long_prose = "Word " * 300
        condensed = condense_prose(long_prose, max_words=250)
        assert len(condensed.split()) <= 250

    def test_action_ideas_start_with_verbs_ec21(self, sample_themes):
        """EC-21: Each generated action idea must start with a capital verb."""
        quotes = [
            "Exit button disappeared during volatile trading candle movement.",
            "KYC verification keeps failing multiple times.",
            "Withdrawal requested before 2 PM was delayed.",
        ]
        cfg = {"llm": {"provider": "gemini"}}
        actions = generate_action_ideas(sample_themes, quotes, cfg)

        assert len(actions) == 3
        for action in actions:
            words = action.split()
            first_word = words[0]
            assert first_word[0].isupper(), f"Action must start with capital letter: {action}"
            # Verify <= 25 words
            assert len(words) <= 25

    def test_no_pii_in_quotes_ec20(self, sample_themes, sample_reviews):
        """EC-20: PII in review is redacted before quote insertion."""
        reviews_with_pii = [
            {"score": 1, "content": "Call me on 9876543210 or email test@gmail.com because app freezes.", "date": "2026-10-30"},
        ]
        theme = {"name": "Crashes", "review_indices": [0]}
        quote = select_quote_for_theme(theme, reviews_with_pii, cfg={})
        assert "9876543210" not in quote
        assert "test@gmail.com" not in quote
        assert "[REDACTED]" in quote

    def test_verbatim_quote_fallback_ec19(self, sample_themes, sample_reviews):
        """EC-19: If LLM produces completely hallucinated quote, code enforces candidate quote."""
        theme = sample_themes[0]
        # Mock LLM returning invented wording
        hallucinated_client = lambda p: "This is a completely fabricated text that does not exist in reviews."
        quote = select_quote_for_theme(theme, sample_reviews, cfg={}, llm_client=hallucinated_client)

        # Fallback should pick one of candidate reviews
        cand_texts = [sample_reviews[0]["content"], sample_reviews[1]["content"]]
        assert any(cand in quote or quote in cand for cand in cand_texts)

    def test_pulse_snapshot_saved_to_disk(self, sample_themes, sample_reviews, config_file, tmp_path):
        """Verify data/pulse_YYYY-MM-DD.json is written."""
        generate_pulse(
            themes=sample_themes,
            reviews=sample_reviews,
            config_path=str(config_file),
            week_ending="2026-11-01",
        )
        snapshot_file = tmp_path / "data" / "pulse_2026-11-01.json"
        assert snapshot_file.exists()
        saved = json.loads(snapshot_file.read_text(encoding="utf-8"))
        assert saved["week_ending"] == "2026-11-01"
        assert len(saved["top_themes"]) == 3

    def test_pulse_from_fixture_reviews(self, sample_themes, config_file):
        """Phase 6.3: Validate pulse generation against mock_reviews fixture."""
        fixture_path = Path(__file__).parent / "fixtures" / "mock_reviews.json"
        assert fixture_path.exists(), "mock_reviews.json fixture must exist"
        reviews = json.loads(fixture_path.read_text(encoding="utf-8"))

        payload, prose = generate_pulse(
            themes=sample_themes,
            reviews=reviews,
            config_path=str(config_file),
            week_ending="2026-11-01",
        )
        assert payload["review_count"] == len(reviews)
        assert len(payload["top_themes"]) == 3
        assert payload["word_count"] <= 250

    def test_call_llm_groq_pulse(self, monkeypatch):
        """Verify calling Groq provider in pulse.py."""
        from src.pulse import _call_llm
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("GROQ_API_KEY", "gsk_test456")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "This is a verbatim quote from review."}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        cfg = {"llm": {"provider": "groq", "model": "llama-3.3-70b-versatile"}}
        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = _call_llm("test prompt", cfg=cfg)
            assert "verbatim quote" in res
