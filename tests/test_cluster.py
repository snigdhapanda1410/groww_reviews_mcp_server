"""
tests/test_cluster.py
─────────────────────────────────────────────────────────────────────────────
Phase 6 / Phase 3 — Unit tests for src/cluster.py

Coverage:
  - Theme schema validation
  - EC-11: Output never exceeds 5 themes (merging smallest themes)
  - EC-12: LLM returns < 3 themes (handled gracefully)
  - EC-13: LLM returns markdown fences around JSON (stripped & parsed)
  - EC-14: Review indices out of bounds (filtered out)
  - EC-15: Duplicate review indices across themes (deduplicated)
  - Sorting: Themes sorted by review_count DESC
  - Error handling: Empty review list raises ClusterError
"""

import json
from pathlib import Path
import pytest

from src.cluster import (
    ClusterError,
    cluster_reviews,
    get_top_themes,
    merge_excess_themes,
    validate_and_sanitize_clusters,
)


@pytest.fixture()
def sample_reviews() -> list[dict]:
    return [
        {"score": 1, "content": "App freezes and crashes when trying to exit trades", "date": "2026-10-30"},
        {"score": 1, "content": "Exit button disappeared during volatile market hours", "date": "2026-10-29"},
        {"score": 2, "content": "KYC verification fails repeatedly with CAMS statement", "date": "2026-10-28"},
        {"score": 1, "content": "Document verification took more than 7 days for PAN", "date": "2026-10-27"},
        {"score": 2, "content": "Withdrawal request stuck for 2 days without notification", "date": "2026-10-26"},
        {"score": 1, "content": "Money deducted but not credited to bank account", "date": "2026-10-25"},
        {"score": 4, "content": "Good app but please add font size increase option", "date": "2026-10-24"},
        {"score": 3, "content": "Charts failed to load even on good network connection", "date": "2026-10-23"},
        {"score": 5, "content": "Great user interface and simple navigation for beginners", "date": "2026-10-22"},
        {"score": 1, "content": "Brokerage and tax charges are hidden and very high", "date": "2026-10-21"},
    ]


class TestClusterReviews:
    def test_empty_reviews_raises_error(self):
        with pytest.raises(ClusterError, match="empty review list"):
            cluster_reviews([])

    def test_cluster_from_fixture_file(self, sample_reviews):
        """Phase 6.2: Validate clustering using external fixture JSON file."""
        fixture_path = Path(__file__).parent / "fixtures" / "mock_cluster_response.json"
        assert fixture_path.exists(), "mock_cluster_response.json fixture must exist"
        raw_fixture = fixture_path.read_text(encoding="utf-8")

        themes = cluster_reviews(sample_reviews, llm_client=lambda p: raw_fixture)
        assert len(themes) == 5
        assert themes[0]["rank"] == 1
        assert "review_indices" in themes[0]

    def test_theme_schema_and_sorting(self, sample_reviews):
        mock_response = json.dumps([
            {"name": "App Crashes", "description": "Crash on exit trade", "review_indices": [0, 1, 7]},
            {"name": "KYC Issues", "description": "KYC verification failure", "review_indices": [2, 3]},
            {"name": "Payments", "description": "Withdrawal delays", "review_indices": [4, 5]},
            {"name": "Charges", "description": "High brokerage", "review_indices": [9]},
        ])
        themes = cluster_reviews(sample_reviews, llm_client=lambda p: mock_response)

        assert len(themes) == 4
        assert themes[0]["rank"] == 1
        assert themes[0]["name"] == "App Crashes"
        assert themes[0]["review_count"] == 3
        # Ensure schema fields exist
        for t in themes:
            assert "name" in t
            assert "description" in t
            assert "review_indices" in t
            assert "review_count" in t
            assert "rank" in t

        # Verify sorted descending
        counts = [t["review_count"] for t in themes]
        assert counts == sorted(counts, reverse=True)

    def test_max_themes_cap_enforced_ec11(self, sample_reviews):
        """EC-11: If LLM returns 7 themes, code must merge down to <= 5 themes."""
        mock_response = json.dumps([
            {"name": "Theme 1", "description": "Desc 1", "review_indices": [0]},
            {"name": "Theme 2", "description": "Desc 2", "review_indices": [1]},
            {"name": "Theme 3", "description": "Desc 3", "review_indices": [2]},
            {"name": "Theme 4", "description": "Desc 4", "review_indices": [3]},
            {"name": "Theme 5", "description": "Desc 5", "review_indices": [4]},
            {"name": "Theme 6", "description": "Desc 6", "review_indices": [5]},
            {"name": "Theme 7", "description": "Desc 7", "review_indices": [6]},
        ])
        themes = cluster_reviews(sample_reviews, llm_client=lambda p: mock_response)
        assert len(themes) <= 5

    def test_markdown_fences_stripped_ec13(self, sample_reviews):
        """EC-13: LLM returning markdown code fences ```json is stripped."""
        raw_json = json.dumps([
            {"name": "Theme A", "description": "Desc A", "review_indices": [0, 1]},
            {"name": "Theme B", "description": "Desc B", "review_indices": [2, 3]},
        ])
        fenced_response = f"```json\n{raw_json}\n```"

        themes = cluster_reviews(sample_reviews, llm_client=lambda p: fenced_response)
        assert len(themes) == 2
        assert themes[0]["name"] == "Theme A"

    def test_out_of_bounds_indices_filtered_ec14(self, sample_reviews):
        """EC-14: Hallucinated / out of bounds indices are dropped."""
        mock_response = json.dumps([
            {"name": "Valid Theme", "description": "Desc", "review_indices": [0, 999, -1, 1]},
        ])
        themes = cluster_reviews(sample_reviews, llm_client=lambda p: mock_response)
        assert len(themes) == 1
        assert themes[0]["review_indices"] == [0, 1]
        assert themes[0]["review_count"] == 2

    def test_duplicate_indices_deduped_ec15(self, sample_reviews):
        """EC-15: Review index appearing across multiple themes is deduped."""
        mock_response = json.dumps([
            {"name": "First Theme", "description": "Desc 1", "review_indices": [0, 1]},
            {"name": "Second Theme", "description": "Desc 2", "review_indices": [1, 2]},
        ])
        themes = cluster_reviews(sample_reviews, llm_client=lambda p: mock_response)
        # Index 1 should only be in First Theme
        assert themes[0]["review_indices"] == [0, 1]
        assert themes[1]["review_indices"] == [2]

    def test_less_than_3_themes_handled_ec12(self, sample_reviews):
        """EC-12: LLM returns only 2 themes; code handles gracefully."""
        mock_response = json.dumps([
            {"name": "Theme One", "description": "Desc 1", "review_indices": [0, 1, 2]},
            {"name": "Theme Two", "description": "Desc 2", "review_indices": [3, 4, 5]},
        ])
        themes = cluster_reviews(sample_reviews, llm_client=lambda p: mock_response)
        assert len(themes) == 2
        top3 = get_top_themes(themes, top_n=3)
        assert len(top3) == 2

    def test_call_llm_groq_provider(self, monkeypatch):
        """Verify calling Groq provider over urllib.request."""
        from src.cluster import _call_llm
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("GROQ_API_KEY", "gsk_test123")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": '[{"name": "Groq Theme", "description": "D", "review_indices": [0]}]'}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        cfg = {"llm": {"provider": "groq", "model": "llama-3.3-70b-versatile"}}
        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = _call_llm("test prompt", cfg=cfg)
            assert "Groq Theme" in res
