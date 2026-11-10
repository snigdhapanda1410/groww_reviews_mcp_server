"""
src/orchestrate.py
─────────────────────────────────────────────────────────────────────────────
Phase 5 — End-to-End Pipeline Orchestrator

Wires together all pipeline layers:
  1. Config & Environment Loading (config.yaml, .env)
  2. Review Ingestion (src/ingest.py) with caching / idempotency (EC-30)
  3. LLM Theme Clustering (src/cluster.py)
  4. Pulse Generation (src/pulse.py) with word-count constraint (EC-18)
  5. Google Docs MCP Publishing (src/mcp_docs.py)
  6. Gmail MCP Notification (src/mcp_gmail.py) with partial failure handling (EC-35)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output encoding across Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yaml
from dotenv import load_dotenv

from src.cluster import cluster_reviews
from src.ingest import fetch_reviews, load_reviews_from_snapshot
from src.mcp_client import DeliveryError, MCPError
from src.mcp_docs import append_pulse_to_doc_sync
from src.mcp_gmail import send_pulse_email_sync
from src.pulse import generate_pulse

load_dotenv()

logger = logging.getLogger("groww_pulse")


class OrchestrationError(RuntimeError):
    """Raised when pipeline orchestration fails."""


def setup_logging(level_name: str = "INFO") -> None:
    """Configure formatted console logging."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def load_config(config_path: str = "config/config.yaml") -> dict:
    """
    Load YAML configuration file with defensive error handling (EC-32).
    """
    path = Path(config_path)
    if not path.exists():
        msg = (
            f"Configuration file not found: {path.resolve()}\n"
            "Please copy config/config.yaml.example to config/config.yaml and configure values."
        )
        logger.error(msg)
        raise FileNotFoundError(msg)

    try:
        with path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            if not isinstance(cfg, dict):
                raise ValueError("Config file is empty or does not contain a YAML mapping.")
            return cfg
    except yaml.YAMLError as exc:
        msg = f"Malformed YAML syntax in {path.resolve()}: {exc}"
        logger.error(msg)
        raise ValueError(msg) from exc


def cleanup_old_snapshots(data_dir: Path | str, max_snapshots: int = 12) -> list[Path]:
    """
    Retain only the most recent `max_snapshots` files for review and pulse snapshots.
    Deletes older JSON snapshots to keep the data/ directory bounded (Phase 7.2).
    """
    path = Path(data_dir)
    if not path.exists():
        return []

    pruned: list[Path] = []
    for prefix in ("reviews_", "pulse_"):
        matching_files = sorted(
            [f for f in path.glob(f"{prefix}*.json") if f.is_file()],
            key=lambda f: f.name,
        )
        if len(matching_files) > max_snapshots:
            to_delete = matching_files[:-max_snapshots]
            for old_file in to_delete:
                try:
                    old_file.unlink()
                    pruned.append(old_file)
                    logger.debug("Deleted old snapshot: %s", old_file)
                except OSError as exc:
                    logger.warning("Could not delete old snapshot %s: %s", old_file, exc)
    return pruned


def run_pipeline(
    config_path: str = "config/config.yaml",
    week_ending: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    skip_email: bool = False,
    skip_docs: bool = False,
    llm_client: Any = None,
    mcp_client: Any = None,
) -> dict[str, Any]:
    """
    Execute the full Groww Reviews Weekly Pulse pipeline.

    Args:
        config_path: Path to config.yaml.
        week_ending: ISO date string (YYYY-MM-DD) overriding snapshot date.
        dry_run: If True, skips MCP remote calls and prints output.
        force: If True, re-fetches reviews even if cached snapshot exists.
        skip_email: If True, skips Gmail dispatch.
        skip_docs: If True, skips Docs append.
        llm_client: Optional mock LLM client for testing.
        mcp_client: Optional mock MCP ClientSession for testing.

    Returns:
        Summary dict containing run metrics, payload, and delivery identifiers.
    """
    cfg = load_config(config_path)
    output_cfg = cfg.get("output", {})
    setup_logging(output_cfg.get("log_level", "INFO"))

    run_date = week_ending or datetime.now().strftime("%Y-%m-%d")
    data_dir = Path(output_cfg.get("data_dir", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("==================================================================")
    logger.info("Starting Groww Weekly Review Pulse Pipeline [week ending %s]", run_date)
    if dry_run:
        logger.info("MODE: DRY-RUN (No external MCP modifications will be executed)")
    logger.info("==================================================================")

    # ── Stage 1: Ingestion & Sanitization (with EC-30 caching) ────────────────
    review_snapshot = data_dir / f"reviews_{run_date}.json"
    if review_snapshot.exists() and not force:
        logger.info("EC-30: Re-run detected for %s. Using cached review snapshot: %s", run_date, review_snapshot)
        reviews = load_reviews_from_snapshot(review_snapshot)
    else:
        logger.info("Stage 1/5: Fetching public Play Store reviews...")
        reviews = fetch_reviews(config_path=config_path, week_ending=run_date)

    logger.info("Stage 1 complete: %d sanitized English reviews ready.", len(reviews))

    # ── Stage 2: LLM Theme Clustering ────────────────────────────────────────
    logger.info("Stage 2/5: Clustering reviews into ranked product themes...")
    themes = cluster_reviews(
        reviews=reviews,
        config_path=config_path,
        config=cfg,
        llm_client=llm_client,
    )
    logger.info("Stage 2 complete: %d themes discovered.", len(themes))
    for t in themes:
        logger.info("  - [%d] %s: %d reviews", t["rank"], t["name"], t["review_count"])

    # ── Stage 3: Pulse Generation & Formatting ────────────────────────────────
    logger.info("Stage 3/5: Generating weekly pulse note, quotes, and action ideas...")
    pulse_payload, pulse_prose = generate_pulse(
        themes=themes,
        reviews=reviews,
        config_path=config_path,
        config=cfg,
        week_ending=run_date,
        llm_client=llm_client,
    )
    word_count = pulse_payload["word_count"]
    logger.info("Stage 3 complete: Pulse formatted successfully (%d words, limit <= 250).", word_count)

    # ── Stage 4: MCP Google Docs Delivery ─────────────────────────────────────
    doc_id = os.getenv("GOOGLE_DOC_ID") or cfg.get("mcp", {}).get("google_doc_id", "1CQmm-g8D41RmTRKwIsGow2eNksmJBEaVvMVrt64abpM")
    doc_url: str | None = None
    docs_result: dict[str, Any] = {}

    if dry_run or skip_docs:
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        logger.info("[DRY-RUN] Would append pulse to Google Doc: %s", doc_url)
        docs_result = {"success": True, "documentId": doc_id, "documentUrl": doc_url, "dry_run": True}
    else:
        logger.info("Stage 4/5: Appending pulse to Google Doc via MCP server...")
        try:
            docs_result = append_pulse_to_doc_sync(
                content=pulse_prose,
                document_id=doc_id,
                config_path=config_path,
                client_session=mcp_client,
            )
            doc_url = docs_result.get("documentUrl")
            logger.info("Stage 4 complete: Google Doc updated -> %s", doc_url)
        except (DeliveryError, MCPError, Exception) as exc:
            logger.error("Stage 4 failed: Could not append pulse to Google Doc: %s", exc)
            raise OrchestrationError(f"Google Docs MCP delivery failed: {exc}") from exc

    # ── Stage 5: MCP Gmail Delivery (with EC-35 partial failure handling) ────
    delivery_cfg = cfg.get("delivery", {})
    recipient = os.getenv("EMAIL_TO") or delivery_cfg.get("email_to", "tinapanda1410@gmail.com")
    email_result: dict[str, Any] = {}
    message_id: str | None = None

    if dry_run or skip_email:
        message_id = "dry-run-msg-id"
        logger.info("[DRY-RUN] Would dispatch pulse email to '%s'", recipient)
        email_result = {"success": True, "messageId": message_id, "to": recipient, "dry_run": True}
    else:
        logger.info("Stage 5/5: Sending pulse email notification to '%s' via MCP...", recipient)
        try:
            email_result = send_pulse_email_sync(
                doc_url=doc_url or f"https://docs.google.com/document/d/{doc_id}/edit",
                pulse_prose=pulse_prose,
                week_ending=run_date,
                to=recipient,
                config_path=config_path,
                client_session=mcp_client,
            )
            message_id = email_result.get("messageId")
            logger.info("Stage 5 complete: Gmail notification sent (Message ID: %s)", message_id)
        except Exception as exc:
            # EC-35: Google Doc succeeded but Gmail failed
            logger.error("EC-35: Gmail dispatch failed after Google Doc was updated.")
            logger.error("Stakeholders can view the published pulse directly at: %s", doc_url)
            logger.error("Gmail error details: %s", exc)
            raise OrchestrationError(
                f"Google Doc updated successfully ({doc_url}), but Gmail dispatch failed: {exc}"
            ) from exc

    # ── Snapshot Retention Cleanup (Phase 7.2) ────────────────────────────────
    retention_limit = int(cfg.get("output", {}).get("retention_snapshots", 12))
    pruned_files = cleanup_old_snapshots(data_dir=data_dir, max_snapshots=retention_limit)
    if pruned_files:
        logger.info("Pruned %d snapshot file(s) exceeding %d-week retention limit.", len(pruned_files), retention_limit)

    # ── Summary & Run Report ──────────────────────────────────────────────────
    logger.info("==================================================================")
    logger.info("✅ Groww Weekly Review Pulse Pipeline Completed Successfully!")
    logger.info("==================================================================")
    logger.info("  Week Ending    : %s", run_date)
    logger.info("  Reviews Ingested: %d", len(reviews))
    logger.info("  Themes Discovered: %d", len(themes))
    logger.info("  Prose Length   : %d words (<= 250 words constraint satisfied)", word_count)
    logger.info("  Google Doc URL : %s", doc_url)
    logger.info("  Gmail Message ID: %s", message_id)
    logger.info("  Review Snapshot: %s", review_snapshot)
    logger.info("  Pulse Snapshot : %s/pulse_%s.json", data_dir, run_date)
    logger.info("==================================================================")

    return {
        "status": "success",
        "week_ending": run_date,
        "review_count": len(reviews),
        "theme_count": len(themes),
        "word_count": word_count,
        "doc_url": doc_url,
        "message_id": message_id,
        "pulse_payload": pulse_payload,
        "pulse_prose": pulse_prose,
        "docs_result": docs_result,
        "email_result": email_result,
        "pruned_snapshots": [str(p) for p in pruned_files],
    }


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Groww Weekly Reviews Pulse Pipeline Orchestrator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--date",
        dest="date",
        type=str,
        default=None,
        help="Override week ending date (YYYY-MM-DD) for backfills or testing.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Run ingestion, clustering, and pulse generation, but skip remote MCP calls.",
    )
    parser.add_argument(
        "--force",
        dest="force",
        action="store_true",
        help="Force re-fetching reviews even if cached snapshot exists for date (EC-30).",
    )
    parser.add_argument(
        "--skip-email",
        dest="skip_email",
        action="store_true",
        help="Append pulse to Google Doc, but skip sending Gmail notification.",
    )
    parser.add_argument(
        "--skip-docs",
        dest="skip_docs",
        action="store_true",
        help="Skip appending pulse to Google Doc, but send Gmail notification.",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        type=str,
        default="config/config.yaml",
        help="Path to YAML configuration file.",
    )
    return parser.parse_args(args)


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    try:
        result = run_pipeline(
            config_path=args.config_path,
            week_ending=args.date,
            dry_run=args.dry_run,
            force=args.force,
            skip_email=args.skip_email,
            skip_docs=args.skip_docs,
        )

        if args.dry_run:
            print("\n" + "=" * 60)
            print("PULSE PROSE OUTPUT (--dry-run):")
            print("=" * 60)
            try:
                print(result["pulse_prose"])
            except UnicodeEncodeError:
                enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
                print(result["pulse_prose"].encode(enc, errors="replace").decode(enc))
            print("=" * 60 + "\n")

        return 0
    except (OrchestrationError, FileNotFoundError, ValueError) as exc:
        logger.error("Pipeline run aborted: %s", exc)
        return 1
    except Exception as exc:
        logger.exception("Unexpected pipeline failure: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
