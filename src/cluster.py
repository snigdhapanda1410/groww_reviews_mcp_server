"""
src/cluster.py
─────────────────────────────────────────────────────────────────────────────
Phase 3 — LLM Theme Clustering Engine

Responsibilities:
  1. Prepare anonymised reviews (rating + sanitized text) for the LLM.
  2. Prompt LLM to group reviews into at most 5 distinct themes.
  3. Validate returned JSON, strip markdown fences, and parse structured output.
  4. Enforce edge-case constraints:
     - EC-11: Auto-merge excess themes down to <= 5.
     - EC-12: Handle < 3 themes gracefully without fabricating fake themes.
     - EC-13: Handle malformed JSON / strip markdown code fences.
     - EC-14: Filter out invalid review indices (bounds check).
     - EC-15: Deduplicate review indices across themes.
  5. Rank and sort themes by volume (review count descending).
  6. Return top themes with schema: {rank, name, description, review_indices, review_count}.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Grounded candidate theme labels based on Groww Play Store review dataset
CANDIDATE_THEMES = [
    "Order Execution & Trading Glitches",
    "App Performance & Freezes",
    "Charts & Technical Analysis",
    "UI Usability & Accessibility",
    "Account Operations & Charges",
]


class ClusterError(RuntimeError):
    """Raised when review clustering fails unrecoverably."""


def _load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences and extraneous text around JSON."""
    cleaned = text.strip()
    # Remove leading ```json or ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    # Remove trailing ```
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _call_llm(
    prompt: str,
    cfg: dict,
    llm_client: Any = None,
) -> str:
    """
    Invoke configured LLM (Gemini or OpenAI) with exponential retry on rate limits.
    If llm_client is provided, use it directly (useful for mocking & testing).
    """
    if llm_client is not None:
        if hasattr(llm_client, "generate_content"):
            res = llm_client.generate_content(prompt)
            return res.text if hasattr(res, "text") else str(res)
        if callable(llm_client):
            return str(llm_client(prompt))
        raise ClusterError(f"Unsupported mock llm_client type: {type(llm_client)}")

    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "gemini").lower()
    model_name = llm_cfg.get("model", "gemini-1.5-pro")
    temperature = float(llm_cfg.get("temperature", 0.2))

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key or api_key.startswith("your_"):
            raise ClusterError(
                "Gemini API key not found or placeholder in .env. "
                "Set GEMINI_API_KEY to run live LLM clustering."
            )
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            return response.text or ""
        except Exception as exc:
            raise ClusterError(f"Gemini LLM call failed: {exc}") from exc

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key.startswith("your_"):
            raise ClusterError(
                "OpenAI API key not found. Set OPENAI_API_KEY in .env."
            )
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model_name,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise ClusterError(f"OpenAI LLM call failed: {exc}") from exc

    elif provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key.startswith("your_"):
            raise ClusterError(
                "Groq API key not found. Set GROQ_API_KEY in .env."
            )
        try:
            import urllib.request
            import urllib.error

            groq_model = model_name if model_name and not model_name.startswith("gemini") else "openai/gpt-oss-120b"
            payload_data = {
                "model": groq_model,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(payload_data).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    return resp_json["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as http_err:
                if http_err.code == 429:
                    logger.warning("Groq rate limit reached (429); waiting 15s to retry...")
                    time.sleep(15)
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        resp_json = json.loads(resp.read().decode("utf-8"))
                        return resp_json["choices"][0]["message"]["content"] or ""
                raise
        except Exception as exc:
            raise ClusterError(f"Groq LLM call failed: {exc}") from exc

    raise ClusterError(f"Unsupported LLM provider: {provider}")


def build_clustering_prompt(reviews: list[dict], max_themes: int = 5) -> str:
    """Format the clustering prompt with numbered review items."""
    formatted_reviews = []
    for i, r in enumerate(reviews):
        score = r.get("score", "N/A")
        content = r.get("content", "").replace("\n", " ").strip()
        formatted_reviews.append(f'[{i}] (Score: {score}/5) "{content}"')

    reviews_block = "\n".join(formatted_reviews)

    return f"""You are an expert product analyst. Below are {len(reviews)} anonymised user reviews 
for the Groww investment app (stocks, mutual funds, IPOs).

Group them into AT MOST {max_themes} distinct themes. For each theme return:
- name: short label (2–4 words)
- description: one sentence summarising the theme
- review_indices: list of 0-based integer indices of reviews belonging to this theme

Candidate theme labels (use if appropriate, but let the data guide you):
{', '.join(CANDIDATE_THEMES)}

Return ONLY a valid JSON array of objects. No explanation or markdown fences outside the JSON.
Schema:
[
  {{
    "name": "Theme Name",
    "description": "One sentence summary.",
    "review_indices": [0, 1, 2]
  }}
]

REVIEWS:
{reviews_block}
"""


def merge_excess_themes(themes: list[dict], max_themes: int = 5) -> list[dict]:
    """
    EC-11: If LLM returns > max_themes themes, iteratively merge the
    smallest two themes until len(themes) <= max_themes.
    """
    if len(themes) <= max_themes:
        return themes

    merged_themes = list(themes)
    while len(merged_themes) > max_themes:
        # Sort ascending by review count to find the two smallest themes
        merged_themes.sort(key=lambda t: len(t.get("review_indices", [])))
        t1 = merged_themes.pop(0)
        t2 = merged_themes.pop(0)

        combined_indices = sorted(
            list(set(t1.get("review_indices", []) + t2.get("review_indices", [])))
        )
        combined_name = f"{t1.get('name', 'Misc')} & {t2.get('name', 'Other')}"
        if len(combined_name) > 35:
            combined_name = "Other / Miscellaneous"

        combined_theme = {
            "name": combined_name,
            "description": f"Combined feedback: {t1.get('description', '')} {t2.get('description', '')}".strip(),
            "review_indices": combined_indices,
            "review_count": len(combined_indices),
        }
        logger.warning(
            "EC-11: Merged excess themes '%s' (%d) and '%s' (%d) into '%s'",
            t1.get("name"),
            len(t1.get("review_indices", [])),
            t2.get("name"),
            len(t2.get("review_indices", [])),
            combined_name,
        )
        merged_themes.append(combined_theme)

    return merged_themes


def validate_and_sanitize_clusters(
    raw_clusters: list[dict],
    num_reviews: int,
    max_themes: int = 5,
) -> list[dict]:
    """
    Validate, bound-check, deduplicate, and sort cluster outputs:
      - Strips invalid review indices (EC-14)
      - Ensures each review index belongs to only one theme (EC-15)
      - Drops themes with 0 reviews
      - Enforces max_themes cap (EC-11)
      - Sorts by review_count descending and assigns rank 1..N
    """
    seen_indices: set[int] = set()
    cleaned_themes: list[dict] = []

    for cluster in raw_clusters:
        if not isinstance(cluster, dict):
            continue

        name = str(cluster.get("name", "Unnamed Theme")).strip()
        desc = str(cluster.get("description", "")).strip()
        raw_indices = cluster.get("review_indices", [])

        if not isinstance(raw_indices, list):
            raw_indices = []

        valid_indices: list[int] = []
        for idx in raw_indices:
            if isinstance(idx, int) and 0 <= idx < num_reviews:
                if idx not in seen_indices:
                    seen_indices.add(idx)
                    valid_indices.append(idx)
            else:
                logger.debug("EC-14: Dropped out-of-bounds review index: %s", idx)

        # Drop themes that have no valid reviews
        if not valid_indices:
            logger.warning("Dropped theme '%s' because it contains 0 valid reviews.", name)
            continue

        cleaned_themes.append({
            "name": name,
            "description": desc,
            "review_indices": sorted(valid_indices),
            "review_count": len(valid_indices),
        })

    if not cleaned_themes:
        raise ClusterError(
            "No valid themes could be extracted from LLM clustering output."
        )

    # EC-11: enforce maximum themes limit
    cleaned_themes = merge_excess_themes(cleaned_themes, max_themes=max_themes)

    # Sort themes descending by review_count
    cleaned_themes.sort(key=lambda t: len(t["review_indices"]), reverse=True)

    # Assign rank 1, 2, ...
    for rank, theme in enumerate(cleaned_themes, start=1):
        theme["rank"] = rank
        theme["review_count"] = len(theme["review_indices"])

    return cleaned_themes


def _heuristic_clusters(reviews: list[dict], max_themes: int = 5) -> list[dict]:
    """Fallback clustering when no API key is provided (for offline / dry-run testing)."""
    theme_buckets = {
        "Order Execution & Trading Glitches": (
            "Exit button failures, adapter disconnections, and trade execution lag during market volatility.",
            ["exit", "button", "adapter", "order", "tpin", "square", "cancel", "disappear", "mtf"]
        ),
        "App Performance & Freezes": (
            "App freezes, technical glitches, and latency experienced during live market hours.",
            ["freeze", "freezes", "hanging", "slow", "stuck", "lag", "glitch", "crash"]
        ),
        "Charts & Technical Analysis": (
            "Chart synchronization discrepancies, candlestick updates, and indicator filters.",
            ["chart", "charts", "candle", "sma", "ema", "filter", "indicator", "preview"]
        ),
        "UI Usability & Accessibility": (
            "User interface adjustments, small font readability, and tablet display formatting.",
            ["font", "size", "tablet", "landscape", "chevron", "ui", "interface", "display"]
        ),
        "Account Operations & Charges": (
            "CAMS statement mismatches, SIP redemption timing, and brokerage fee transparency.",
            ["cams", "kyc", "pan", "sip", "mutual", "brokerage", "charge", "charges", "tax", "fee"]
        ),
    }

    raw_clusters = []
    assigned_indices = set()

    for name, (desc, keywords) in theme_buckets.items():
        indices = []
        for idx, r in enumerate(reviews):
            if idx in assigned_indices:
                continue
            content = r.get("content", "").lower()
            if any(k in content for k in keywords):
                indices.append(idx)
                assigned_indices.add(idx)

        if indices:
            raw_clusters.append({
                "name": name,
                "description": desc,
                "review_indices": indices,
            })

    # Catch remaining reviews
    remaining = [idx for idx in range(len(reviews)) if idx not in assigned_indices]
    if remaining:
        raw_clusters.append({
            "name": "General Feedback & Usability",
            "description": "General user experiences and beginner-friendly interface comments.",
            "review_indices": remaining,
        })

    return validate_and_sanitize_clusters(raw_clusters, num_reviews=len(reviews), max_themes=max_themes)


def cluster_reviews(
    reviews: list[dict],
    config_path: str = "config/config.yaml",
    config: dict | None = None,
    llm_client: Any = None,
) -> list[dict]:
    """
    Cluster a list of sanitized reviews into <= 5 ranked themes.

    Args:
        reviews: List of sanitized review dictionaries.
        config_path: Path to config.yaml if config dict is not provided.
        config: Optional loaded configuration dictionary.
        llm_client: Optional mock or real LLM client for testing.

    Returns:
        List of theme dictionaries sorted by volume descending:
        [
          {
            "rank": 1,
            "name": "App Performance",
            "description": "Users report freezing and lag during trading hours.",
            "review_indices": [0, 4, 12],
            "review_count": 3
          }, ...
        ]

    Raises:
        ClusterError: If clustering fails or no valid themes are produced.
    """
    if not reviews:
        raise ClusterError("Cannot cluster empty review list (0 reviews provided).")

    cfg = config if config is not None else _load_config(config_path)
    pulse_cfg = cfg.get("pulse", {})
    max_themes = int(pulse_cfg.get("max_themes", 5))

    # Offline / dry-run fallback if no API key is configured for active provider
    def _has_valid_api_key(c: dict) -> bool:
        prov = c.get("llm", {}).get("provider", "gemini").lower()
        if prov == "gemini":
            k = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        elif prov == "groq":
            k = os.getenv("GROQ_API_KEY")
        elif prov == "openai":
            k = os.getenv("OPENAI_API_KEY")
        else:
            k = None
        return bool(k and not k.startswith("your_"))

    if llm_client is None and not _has_valid_api_key(cfg):
        logger.warning(
            "No valid API key detected for provider '%s'; utilizing heuristic clustering fallback.",
            cfg.get("llm", {}).get("provider", "gemini"),
        )
        return _heuristic_clusters(reviews, max_themes=max_themes)

    clustering_reviews = reviews
    provider = cfg.get("llm", {}).get("provider", "gemini").lower()
    if provider == "groq" and len(reviews) > 35:
        # Sample proportionally across star ratings to stay within Groq free-tier 8,000 TPM limit
        by_score: dict[int, list[dict]] = {}
        for r in reviews:
            by_score.setdefault(r.get("score", 3), []).append(r)
        sampled = []
        for score, rev_list in by_score.items():
            k = max(1, int(len(rev_list) / len(reviews) * 35))
            sampled.extend(rev_list[:k])
        clustering_reviews = sampled[:35]
        logger.info("Sampled %d reviews for Groq clustering to respect 8k TPM limit.", len(clustering_reviews))

    prompt = build_clustering_prompt(clustering_reviews, max_themes=max_themes)
    logger.info("Sending %d reviews to LLM for theme clustering...", len(clustering_reviews))

    raw_response = _call_llm(prompt, cfg, llm_client=llm_client)

    # Clean potential markdown fences (EC-13)
    json_text = _clean_json_response(raw_response)

    try:
        raw_clusters = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.warning("EC-13: Initial JSON decode failed: %s. Retrying clean...", exc)
        # Try extracting JSON array substring
        match = re.search(r"\[.*\]", json_text, flags=re.DOTALL)
        if match:
            try:
                raw_clusters = json.loads(match.group(0))
            except json.JSONDecodeError as second_exc:
                raise ClusterError(
                    f"LLM returned invalid JSON: {second_exc}\nRaw response:\n{raw_response[:300]}"
                ) from second_exc
        else:
            raise ClusterError(
                f"LLM returned invalid JSON (no array found): {exc}\nRaw response:\n{raw_response[:300]}"
            ) from exc

    if not isinstance(raw_clusters, list):
        raise ClusterError(
            f"Expected JSON array of themes, got {type(raw_clusters).__name__}"
        )

    themes = validate_and_sanitize_clusters(
        raw_clusters=raw_clusters,
        num_reviews=len(clustering_reviews),
        max_themes=max_themes,
    )

    logger.info("Successfully clustered %d reviews into %d themes.", len(reviews), len(themes))
    return themes


def get_top_themes(themes: list[dict], top_n: int = 3) -> list[dict]:
    """Return top N themes sorted by volume (EC-12 handles < N themes)."""
    if not themes:
        return []
    return themes[:top_n]
