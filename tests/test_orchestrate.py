"""
tests/test_orchestrate.py
─────────────────────────────────────────────────────────────────────────────
Phase 5 / Phase 6 — Unit tests for Pipeline Orchestrator (src/orchestrate.py)

Coverage:
  - Happy path / Dry-run execution
  - Date override (--date YYYY-MM-DD)
  - EC-30: Idempotent re-run using cached reviews snapshot
  - EC-32: Missing or malformed config.yaml error handling
  - EC-35: Partial run failure (Docs succeeds, Gmail fails)
  - CLI argument parsing
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import yaml

from src.orchestrate import (
    OrchestrationError,
    cleanup_old_snapshots,
    load_config,
    parse_args,
    run_pipeline,
)


@pytest.fixture()
def config_data(tmp_path: Path) -> tuple[Path, dict]:
    data_dir = tmp_path / "data"
    cfg = {
        "review": {
            "app_id": "com.nextbillion.groww",
            "country": "in",
            "language": "en",
            "weeks_back": 10,
            "max_reviews": 50,
            "min_words": 8,
            "strip_emojis": True,
            "english_only": True,
        },
        "llm": {
            "provider": "gemini",
            "model": "gemini-1.5-pro",
            "temperature": 0.2,
        },
        "pulse": {
            "max_themes": 5,
            "top_themes": 3,
            "quotes_count": 3,
            "action_ideas_count": 3,
            "max_words": 250,
        },
        "mcp": {
            "server_url": "https://mcpservergroww.vercel.app/mcp",
            "health_url": "https://mcpservergroww.vercel.app/health",
            "google_doc_id": "test_doc_id_12345",
        },
        "delivery": {
            "email_to": "test@example.com",
            "doc_title_prefix": "Groww Weekly Pulse",
            "email_subject_prefix": "[Groww Pulse] Weekly Summary",
        },
        "output": {
            "data_dir": str(data_dir),
            "log_level": "DEBUG",
        },
    }
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(cfg))
    return cfg_file, cfg


@pytest.fixture()
def sample_reviews() -> list[dict]:
    return [
        {"score": 1, "content": f"Review {i}: App crashes and exit button disappears during trading volatility.", "date": "2026-10-30"}
        for i in range(10)
    ]


@pytest.fixture()
def sample_themes() -> list[dict]:
    return [
        {
            "rank": 1,
            "name": "Trading Crashes",
            "description": "Exit button disappears during market hours.",
            "review_indices": [0, 1, 2, 3],
            "review_count": 4,
        },
        {
            "rank": 2,
            "name": "Order Lag",
            "description": "Orders delayed during peak times.",
            "review_indices": [4, 5, 6],
            "review_count": 3,
        },
        {
            "rank": 3,
            "name": "Chart Sync",
            "description": "Candle charts failing to update.",
            "review_indices": [7, 8, 9],
            "review_count": 3,
        },
    ]


class TestOrchestrator:
    def test_load_config_missing_file_raises_ec32(self, tmp_path):
        """EC-32: Missing config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_load_config_malformed_yaml_raises_ec32(self, tmp_path):
        """EC-32: Malformed YAML syntax raises ValueError."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("invalid: [yaml: unclosed")
        with pytest.raises(ValueError, match="Malformed YAML syntax"):
            load_config(str(bad_file))

    def test_dry_run_pipeline_execution(self, config_data, sample_reviews, sample_themes):
        cfg_file, cfg = config_data

        with patch("src.orchestrate.fetch_reviews", return_value=sample_reviews), \
             patch("src.orchestrate.cluster_reviews", return_value=sample_themes):

            result = run_pipeline(
                config_path=str(cfg_file),
                week_ending="2026-11-01",
                dry_run=True,
            )

            assert result["status"] == "success"
            assert result["week_ending"] == "2026-11-01"
            assert result["review_count"] == 10
            assert result["theme_count"] == 3
            assert result["word_count"] <= 250
            assert "test_doc_id_12345" in result["doc_url"]
            assert result["message_id"] == "dry-run-msg-id"
            assert result["docs_result"]["dry_run"] is True
            assert result["email_result"]["dry_run"] is True

    def test_date_override_and_snapshot_persistence(self, config_data, sample_reviews, sample_themes):
        cfg_file, cfg = config_data
        data_dir = Path(cfg["output"]["data_dir"])

        with patch("src.orchestrate.fetch_reviews", return_value=sample_reviews), \
             patch("src.orchestrate.cluster_reviews", return_value=sample_themes):

            result = run_pipeline(
                config_path=str(cfg_file),
                week_ending="2026-10-25",
                dry_run=True,
            )

            assert result["week_ending"] == "2026-10-25"
            pulse_file = data_dir / "pulse_2026-10-25.json"
            assert pulse_file.exists()

    def test_rerun_uses_cached_snapshot_ec30(self, config_data, sample_reviews, sample_themes):
        """EC-30: If reviews snapshot exists for date, reuse it instead of scraping."""
        cfg_file, cfg = config_data
        data_dir = Path(cfg["output"]["data_dir"])
        data_dir.mkdir(parents=True, exist_ok=True)

        cached_file = data_dir / "reviews_2026-11-01.json"
        cached_file.write_text(json.dumps({
            "fetched_at": "2026-11-01T00:00:00",
            "app_id": "com.nextbillion.groww",
            "week_ending": "2026-11-01",
            "review_count": len(sample_reviews),
            "reviews": sample_reviews,
        }))

        mock_fetch = MagicMock()
        with patch("src.orchestrate.fetch_reviews", mock_fetch), \
             patch("src.orchestrate.cluster_reviews", return_value=sample_themes):

            result = run_pipeline(
                config_path=str(cfg_file),
                week_ending="2026-11-01",
                dry_run=True,
                force=False,
            )

            # fetch_reviews should NOT be called because cached file exists
            mock_fetch.assert_not_called()
            assert result["review_count"] == 10

    def test_partial_failure_ec35_docs_succeeds_gmail_fails(self, config_data, sample_reviews, sample_themes):
        """EC-35: Google Doc succeeds but Gmail fails -> logs doc URL, raises OrchestrationError."""
        cfg_file, _ = config_data

        with patch("src.orchestrate.fetch_reviews", return_value=sample_reviews), \
             patch("src.orchestrate.cluster_reviews", return_value=sample_themes), \
             patch("src.orchestrate.append_pulse_to_doc_sync", return_value={"success": True, "documentUrl": "https://docs.google.com/doc1"}), \
             patch("src.orchestrate.send_pulse_email_sync", side_effect=Exception("Gmail quota exceeded")):

            with pytest.raises(OrchestrationError, match="Gmail dispatch failed"):
                run_pipeline(
                    config_path=str(cfg_file),
                    week_ending="2026-11-01",
                    dry_run=False,
                )

    def test_parse_args(self):
        args = parse_args(["--date", "2026-10-31", "--dry-run", "--force", "--skip-email"])
        assert args.date == "2026-10-31"
        assert args.dry_run is True
        assert args.force is True
        assert args.skip_email is True
        assert args.skip_docs is False

    def test_cleanup_old_snapshots_prunes_older_than_retention(self, tmp_path):
        """Phase 7.2: Verify cleanup_old_snapshots retains only max_snapshots."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create 15 reviews and pulse files
        for i in range(1, 16):
            day = f"{i:02d}"
            (data_dir / f"reviews_2026-10-{day}.json").write_text("{}")
            (data_dir / f"pulse_2026-10-{day}.json").write_text("{}")

        # Cleanup keeping only 5 snapshots
        pruned = cleanup_old_snapshots(data_dir, max_snapshots=5)

        # 10 reviews + 10 pulse files should have been pruned
        assert len(pruned) == 20

        remaining_reviews = list(data_dir.glob("reviews_*.json"))
        remaining_pulse = list(data_dir.glob("pulse_*.json"))
        assert len(remaining_reviews) == 5
        assert len(remaining_pulse) == 5

        # Check that the newest ones were kept (days 11 to 15)
        expected_remaining = {f"reviews_2026-10-{i:02d}.json" for i in range(11, 16)}
        actual_remaining = {f.name for f in remaining_reviews}
        assert actual_remaining == expected_remaining

