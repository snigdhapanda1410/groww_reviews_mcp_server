"""
src/ingest.py
─────────────────────────────────────────────────────────────────────────────
Phase 2 — Review Ingestion Layer

Responsibilities:
  1. Fetch public Groww Play Store reviews via google-play-scraper
     (no login, no session cookies, no ToS-violating automation)
  2. Filter to the configured date window (weeks_back)
  3. Strip all PII fields (userName, userImage, reviewId, …)
  4. Redact PII patterns inside review text (email, phone, Aadhaar)
  5. Remove all emoji characters and dingbats from review text
  6. Filter to reviews having strictly more than 8 words
  7. Filter to English reviews only (drop Hindi, Hinglish, regional/other)
  8. Truncate extremely long review texts to avoid huge LLM prompts
  9. Deduplicate reviews
  10. Save a clean JSON snapshot to data/reviews_YYYY-MM-DD.json
  11. Return the sanitised review list to the caller

Edge cases handled (ref: edge-cases.md):
  EC-01  Zero reviews → IngestError
  EC-02  Fewer than 3 reviews → widen window up to max_weeks, then error
  EC-03  Scraper network error → exponential backoff (3 attempts)
  EC-04  Non-English reviews (Hindi/Hinglish/other) → filtered out
  EC-05  Empty / short (<= 8 words) content → filtered out
  EC-06  Duplicate reviews → deduplicated on (content_hash, date)
  EC-07  PII in content → regex-redacted to [REDACTED]
  EC-08  Missing / malformed date → kept with date="unknown"; future dates dropped
  EC-09  Content > MAX_CONTENT_CHARS → truncated to MAX_CONTENT_CHARS + "..."
  EC-33  data/ directory missing → auto-created
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from google_play_scraper import Sort, reviews as gps_reviews

# ─── Constants ────────────────────────────────────────────────────────────────

# Fields to keep from the raw scraper response (everything else is dropped)
KEEP_FIELDS = {"score", "content", "at", "reviewCreatedVersion"}

# Hard character cap per review content (EC-09)
MAX_CONTENT_CHARS = 500

# Absolute maximum weeks we'll ever widen the window to (EC-02)
MAX_WEEKS_FALLBACK = 16

# Retry settings for the scraper (EC-03)
RETRY_DELAYS = [5, 15, 45]  # seconds between attempts

# PII regex patterns (EC-07)
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
)
_PHONE_RE = re.compile(
    r"(\+91[\-\s]?)?[6-9]\d{9}"
)
_AADHAAR_RE = re.compile(
    r"\b\d{4}\s\d{4}\s\d{4}\b"
)

# Emoji & symbols regex pattern
_EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff]"
    r"|[\u2600-\u27BF]"
    r"|[\u2300-\u23FF]"
    r"|[\u2B50\u2B55]"
    r"|[\u200D\uFE0E\uFE0F\u20E3]"
)

# Distinctive Hindi and Romanized Hindi (Hinglish) words (not clashing with common English)
_DISTINCT_HINGLISH_WORDS = {
    "hai", "hain", "karta", "karti", "karte", "karna", "karega", "karenge", "kare",
    "nahi", "nhi", "nahin", "mat", "na",
    "hota", "hoti", "hote", "hua", "hue", "hui", "hoga", "hogi", "honge",
    "bhi", "bhot", "bahut", "baut", "bohot", "accha", "acha", "achha", "bekar", "ghatiya",
    "ekdam", "ekdm", "chahiye", "wala", "wali", "wale", "karo", "kijiye", "kro",
    "mujhe", "mera", "meri", "mere", "hum", "hamara", "apka", "apke",
    "kuch", "sabse", "pehle", "baad", "paise", "paisa", "rupaye", "chor",
    "lutera", "farji", "liye", "mein", "mai", "se", "ko", "ka", "ki", "ke",
    "par", "pr", "lekin", "kyuki", "kyun", "kya", "toh", "ye", "yehi", "wo", "woh",
    "batao", "lagte", "raha", "rahi", "rahe", "aasan", "sare", "krne", "bje",
    "kroge", "mene", "kaa", "dala", "chaan", "ahhe", "pan", "mast",
}

_COMMON_ENGLISH_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not", "on", "with",
    "he", "as", "you", "do", "at", "this", "but", "his", "by", "from", "they", "we", "say", "her",
    "she", "or", "an", "will", "my", "one", "all", "would", "there", "their", "what", "so", "up",
    "out", "if", "about", "who", "get", "which", "go", "me", "when", "make", "can", "like", "time",
    "no", "just", "him", "know", "take", "people", "into", "year", "your", "good", "some", "could",
    "them", "see", "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first", "well", "way", "even",
    "new", "want", "because", "any", "these", "give", "day", "most", "us", "app", "groww", "stock",
    "stocks", "fund", "funds", "mutual", "trading", "money", "loss", "order", "option", "account",
    "service", "broker", "brokerage", "update", "worst", "best", "very", "problem", "glitch",
    "support", "feature", "issues", "charges", "market", "sell", "buy", "exit", "price", "rate",
    "simple", "user", "interface", "easy", "smooth", "fast", "slow", "crashes", "shows", "trade",
}

logger = logging.getLogger(__name__)


# ─── Custom Exceptions ─────────────────────────────────────────────────────────


class IngestError(RuntimeError):
    """Raised when review ingestion fails unrecoverably."""


# ─── Config Loading ────────────────────────────────────────────────────────────


def _load_config(config_path: str = "config/config.yaml") -> dict:
    """Load and return the pipeline YAML config."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path.resolve()}\n"
            "Run setup: copy config/config.yaml.example and fill values."
        )
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── PII Utilities ─────────────────────────────────────────────────────────────


def redact_pii(text: str) -> tuple[str, int]:
    """
    Scan *text* for email, phone, and Aadhaar patterns and replace each
    match with ``[REDACTED]``.

    Returns:
        (redacted_text, count_of_redactions)
    """
    count = 0
    for pattern in (_EMAIL_RE, _PHONE_RE, _AADHAAR_RE):
        new_text, n = pattern.subn("[REDACTED]", text)
        text = new_text
        count += n
    return text, count


def remove_emojis(text: str) -> str:
    """
    Remove all emoji characters, dingbats, and pictographs from text,
    normalising any leftover consecutive whitespace.
    """
    cleaned = _EMOJI_RE.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def has_non_latin_script(text: str) -> bool:
    """
    Return True if text contains characters from Devanagari or other
    regional non-Latin scripts (Hindi, Bengali, Tamil, etc.).
    """
    for char in text:
        cp = ord(char)
        # Devanagari, Bengali, Gurmukhi, Gujarati, Tamil, Telugu, Kannada, Malayalam, Arabic
        if 0x0900 <= cp <= 0x0D7F or 0x0600 <= cp <= 0x06FF:
            return True
    return False


def is_english(text: str) -> bool:
    """
    Determine if review text is written in English:
      1. Rejects non-Latin scripts (e.g. Hindi Devanagari).
      2. Rejects Romanized Hindi / Hinglish.
      3. Verifies English vocabulary or langdetect confirmation.
    """
    if has_non_latin_script(text):
        return False

    tokens = [w.lower() for w in re.findall(r"\b[a-zA-Z]+\b", text)]
    if not tokens:
        return False

    # Check for Romanized Hindi / Hinglish keywords
    hinglish_count = sum(1 for t in tokens if t in _DISTINCT_HINGLISH_WORDS)
    if hinglish_count >= 2 or (len(tokens) >= 5 and hinglish_count / len(tokens) >= 0.15):
        return False

    # Check common English vocabulary overlap
    english_count = sum(1 for t in tokens if t in _COMMON_ENGLISH_WORDS)
    if english_count / len(tokens) >= 0.30:
        return True

    # Fallback to langdetect if available
    try:
        from langdetect import detect_langs
        for l in detect_langs(text):
            if l.lang == "en" and l.prob >= 0.5:
                return True
        return False
    except Exception:
        return False


# ─── Scraper Wrapper ───────────────────────────────────────────────────────────


def _fetch_raw(
    app_id: str,
    lang: str,
    country: str,
    count: int,
) -> list[dict]:
    """
    Call google-play-scraper with exponential-backoff retry (EC-03).

    Raises:
        IngestError: if all retry attempts fail.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS, start=1):
        if delay:
            logger.warning(
                "Scraper attempt %d/%d failed — retrying in %ds…",
                attempt - 1,
                len(RETRY_DELAYS) + 1,
                delay,
            )
            time.sleep(delay)
        try:
            result, _ = gps_reviews(
                app_id,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=count,
            )
            logger.info("Fetched %d raw reviews from Play Store.", len(result))
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error("Scraper error (attempt %d): %s", attempt, exc)
            last_exc = exc

    raise IngestError(
        f"Play Store fetch failed after {len(RETRY_DELAYS) + 1} attempts: {last_exc}"
    )


# ─── Date Utilities ────────────────────────────────────────────────────────────


def _parse_date(at_value: Any) -> str | None:
    """
    Convert the ``at`` field from the scraper (datetime or None) to an
    ISO date string ``YYYY-MM-DD``, or ``None`` if it cannot be parsed.
    """
    if at_value is None:
        return None
    if isinstance(at_value, datetime):
        return at_value.strftime("%Y-%m-%d")
    # Some versions return a string
    try:
        return datetime.fromisoformat(str(at_value)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _cutoff_date(weeks_back: int) -> datetime:
    """Return a timezone-aware UTC datetime N weeks ago."""
    return datetime.now(tz=timezone.utc) - timedelta(weeks=weeks_back)


# ─── Sanitisation Pipeline ─────────────────────────────────────────────────────


def _sanitise_one(
    raw: dict,
    min_words: int = 8,
    strip_emojis: bool = True,
    english_only: bool = True,
) -> dict | None:
    """
    Process a single raw scraper record:
      - Keep only KEEP_FIELDS
      - Redact PII in content (EC-07)
      - Strip emojis from content
      - Drop reviews with <= min_words words (keeps > min_words, e.g. > 8 words)
      - Filter out Hindi / non-English reviews
      - Drop reviews with empty or near-empty content (< 10 chars) (EC-05)
      - Truncate long content to MAX_CONTENT_CHARS (EC-09)
      - Parse and validate date (EC-08)

    Returns:
        A clean review dict, or None if the review should be discarded.
    """
    # Extract only allowed fields
    content: str = (raw.get("content") or "").strip()
    score: int = raw.get("score", 0)
    at_raw = raw.get("at")
    version: str = raw.get("reviewCreatedVersion") or "unknown"

    if not content:
        return None

    # EC-07: redact PII in content
    content, redactions = redact_pii(content)
    if redactions:
        logger.debug("Redacted %d PII pattern(s) in a review.", redactions)

    # Emoji removal
    if strip_emojis:
        content = remove_emojis(content)

    # EC-05: skip empty or near-empty content
    if len(content) < 10:
        return None

    # Word count filter: keep reviews with strictly more than min_words (e.g. > 8 words)
    if min_words > 0 and len(content.split()) <= min_words:
        return None

    # Language filter: keep English reviews, drop Hindi / Hinglish / other
    if english_only and not is_english(content):
        return None

    # EC-09: truncate extremely long content
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "…"

    # EC-08: parse date
    date_str = _parse_date(at_raw)
    if date_str is None:
        date_str = "unknown"
        logger.debug("Review with unparseable date kept with date='unknown'.")

    return {
        "score": score,
        "content": content,
        "date": date_str,
        "version": version,
    }


def _in_window(review: dict, cutoff: datetime) -> bool:
    """Return True if the review date falls on or after *cutoff*."""
    date_str = review.get("date", "unknown")
    if date_str == "unknown":
        return True  # keep reviews with unknown dates (EC-08)
    try:
        review_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        now = datetime.now(tz=timezone.utc)
        # EC-08: drop future dates
        if review_dt > now:
            return False
        return review_dt >= cutoff
    except ValueError:
        return True  # keep if we can't parse


def _dedup(reviews: list[dict]) -> list[dict]:
    """
    Remove duplicate reviews on (sha256(content), date). (EC-06)
    Preserves original order; first occurrence wins.
    """
    seen: set[str] = set()
    unique: list[dict] = []
    for r in reviews:
        key = hashlib.sha256(
            (r["content"] + r["date"]).encode()
        ).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    removed = len(reviews) - len(unique)
    if removed:
        logger.info("Removed %d duplicate review(s).", removed)
    return unique


# ─── Public API ────────────────────────────────────────────────────────────────


def fetch_reviews(
    config_path: str = "config/config.yaml",
    week_ending: str | None = None,
) -> list[dict]:
    """
    Full ingestion pipeline:

    1. Load config
    2. Fetch raw reviews (with retry)
    3. Sanitise, filter by date window, deduplicate
    4. Handle EC-01 (zero reviews) and EC-02 (<3 reviews, widen window)
    5. Save snapshot to data/
    6. Return sanitised review list

    Args:
        config_path: Path to config.yaml (default: ``"config/config.yaml"``).
        week_ending:  ISO date string ``YYYY-MM-DD`` for the snapshot filename.
                      Defaults to today's date.

    Returns:
        List of sanitised review dicts: ``{score, content, date, version}``

    Raises:
        IngestError: on unrecoverable fetch or insufficient review count.
    """
    cfg = _load_config(config_path)
    review_cfg = cfg["review"]
    output_cfg = cfg["output"]

    app_id: str = review_cfg["app_id"]
    lang: str = review_cfg.get("language", "en")
    country: str = review_cfg.get("country", "in")
    max_count: int = review_cfg.get("max_reviews", 500)
    weeks_back: int = review_cfg.get("weeks_back", 10)
    min_words: int = review_cfg.get("min_words", 8)
    strip_emojis: bool = review_cfg.get("strip_emojis", True)
    english_only: bool = review_cfg.get("english_only", True)

    data_dir = Path(output_cfg.get("data_dir", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)  # EC-33

    run_date = week_ending or datetime.now().strftime("%Y-%m-%d")

    logger.info(
        "Starting ingestion — app_id=%s, weeks_back=%d, country=%s",
        app_id,
        weeks_back,
        country,
    )

    # ── Fetch (with possible window widening for EC-02) ──────────────────────
    widened_weeks = min(weeks_back + 2, MAX_WEEKS_FALLBACK)
    attempt_list = [weeks_back] if weeks_back >= MAX_WEEKS_FALLBACK else [weeks_back, widened_weeks]

    for attempt_weeks in attempt_list:
        raw_reviews = _fetch_raw(app_id, lang, country, max_count)
        cutoff = _cutoff_date(attempt_weeks)

        # Sanitise each record
        sanitised: list[dict] = []
        for raw in raw_reviews:
            clean = _sanitise_one(
                raw,
                min_words=min_words,
                strip_emojis=strip_emojis,
                english_only=english_only,
            )
            if clean is None:
                continue
            if _in_window(clean, cutoff):
                sanitised.append(clean)

        sanitised = _dedup(sanitised)

        # EC-01: no reviews at all
        if len(sanitised) == 0:
            raise IngestError(
                f"No reviews fetched for window (app_id={app_id}, "
                f"weeks_back={attempt_weeks}, country={country}). "
                "Check app_id and network connectivity."
            )

        # EC-02: fewer than 3 — try widened window once
        if len(sanitised) < 3:
            if attempt_weeks < widened_weeks:
                logger.warning(
                    "Only %d review(s) found in %d-week window — "
                    "widening to %d weeks…",
                    len(sanitised),
                    attempt_weeks,
                    widened_weeks,
                )
                continue  # retry with wider window
            raise IngestError(
                f"Insufficient reviews: {len(sanitised)} found "
                f"(minimum 3 required) after widening to {attempt_weeks} weeks."
            )

        break  # enough reviews — proceed

    logger.info(
        "Ingested %d review(s) after sanitisation (window: %d weeks).",
        len(sanitised),
        attempt_weeks,
    )

    # ── Save snapshot ─────────────────────────────────────────────────────────
    snapshot_path = data_dir / f"reviews_{run_date}.json"
    snapshot = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "app_id": app_id,
        "week_ending": run_date,
        "review_count": len(sanitised),
        "reviews": sanitised,
    }
    with snapshot_path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    logger.info("Snapshot saved → %s", snapshot_path)
    return sanitised


def load_reviews_from_snapshot(
    snapshot_path: str | Path,
) -> list[dict]:
    """
    Load a previously saved review snapshot from disk.
    Used by orchestrate.py when re-running on the same date (EC-30).

    Returns the ``reviews`` list from the snapshot JSON.
    """
    path = Path(snapshot_path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    reviews = data.get("reviews", [])
    logger.info("Loaded %d review(s) from snapshot: %s", len(reviews), path)
    return reviews


