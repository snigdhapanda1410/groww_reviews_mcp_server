"""
src/pulse.py
─────────────────────────────────────────────────────────────────────────────
Phase 3 — Pulse Generator

Responsibilities:
  1. Select representative verbatim quotes for top themes (EC-19, EC-20, EC-22).
  2. Generate concrete next steps / action ideas starting with verbs (EC-21, EC-23).
  3. Assemble structured pulse payload:
     { week_ending, review_count, top_themes: [{rank, name, description, review_count, quote}],
       action_ideas, word_count }
  4. Format human-readable one-page pulse prose (<= 250 words) (EC-18).
  5. Auto-condense prose if it exceeds 250 words.
  6. Save pulse payload snapshot to data/pulse_YYYY-MM-DD.json.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.ingest import redact_pii

load_dotenv()

logger = logging.getLogger(__name__)

# Fallback verbs to enforce starting with a capital verb (EC-21)
COMMON_VERBS = {
    "fix", "add", "improve", "streamline", "redesign", "optimize", "accelerate",
    "enhance", "simplify", "resolve", "update", "audit", "automate", "clarify",
    "ensure", "prevent", "introduce", "enable", "upgrade", "investigate",
}


class PulseError(RuntimeError):
    """Raised when pulse generation fails unrecoverably."""


def _load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _call_llm(
    prompt: str,
    cfg: dict,
    llm_client: Any = None,
) -> str:
    """Invoke LLM or mock client."""
    if llm_client is not None:
        if hasattr(llm_client, "generate_content"):
            res = llm_client.generate_content(prompt)
            return res.text if hasattr(res, "text") else str(res)
        if callable(llm_client):
            return str(llm_client(prompt))
        raise PulseError(f"Unsupported mock llm_client type: {type(llm_client)}")

    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "gemini").lower()
    model_name = llm_cfg.get("model", "gemini-1.5-pro")
    temperature = float(llm_cfg.get("temperature", 0.2))

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key or api_key.startswith("your_"):
            raise PulseError(
                "Gemini API key not found in .env. Set GEMINI_API_KEY to run live pulse generation."
            )
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            return response.text or ""
        except Exception as exc:
            raise PulseError(f"Gemini LLM call failed in pulse: {exc}") from exc

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key.startswith("your_"):
            raise PulseError("OpenAI API key not found. Set OPENAI_API_KEY in .env.")
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
            raise PulseError(f"OpenAI LLM call failed in pulse: {exc}") from exc

    elif provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key.startswith("your_"):
            raise PulseError("Groq API key not found. Set GROQ_API_KEY in .env.")
        try:
            import json
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
                    logger.warning("Groq rate limit reached in pulse (429); waiting 12s to retry...")
                    time.sleep(12)
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        resp_json = json.loads(resp.read().decode("utf-8"))
                        return resp_json["choices"][0]["message"]["content"] or ""
                raise
        except Exception as exc:
            raise PulseError(f"Groq LLM call failed in pulse: {exc}") from exc

    raise PulseError(f"Unsupported LLM provider: {provider}")


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences and whitespace from JSON response."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _sanitize_quote(quote: str, candidate_reviews: list[str]) -> str:
    """
    Sanitize and enforce verbatim fidelity for a selected quote (EC-19, EC-20):
      - Strips surrounding quotes.
      - Scans for PII and redacts (EC-20).
      - Caps word count to <= 40 words.
      - Verifies quote is grounded in candidate reviews; falls back to exact snippet if paraphrased.
    """
    clean_quote = quote.strip().strip('"').strip("'").strip()
    clean_quote, _ = redact_pii(clean_quote)

    # EC-19: Verbatim grounding check
    # Check if clean_quote or part of it appears in any candidate review
    grounded = any(clean_quote.lower() in cand.lower() or cand.lower() in clean_quote.lower() for cand in candidate_reviews)

    if not grounded and candidate_reviews:
        # Fallback to the most representative candidate review if LLM paraphrased
        logger.warning("EC-19: LLM paraphrased quote '%s'. Falling back to verbatim review.", clean_quote[:50])
        # Pick the candidate review closest in length to 15-30 words
        clean_quote = min(
            candidate_reviews,
            key=lambda c: abs(len(c.split()) - 20) if len(c.split()) >= 5 else 999
        )
        clean_quote, _ = redact_pii(clean_quote)

    # Word count limit (max 40 words)
    words = clean_quote.split()
    if len(words) > 40:
        clean_quote = " ".join(words[:40]) + "…"

    return clean_quote


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


def select_quote_for_theme(
    theme: dict,
    reviews: list[dict],
    cfg: dict,
    llm_client: Any = None,
) -> str:
    """
    Select a single verbatim quote (<= 40 words) for a theme.
    """
    indices = theme.get("review_indices", [])
    candidate_reviews = [
        reviews[i]["content"].strip()
        for i in indices
        if 0 <= i < len(reviews) and reviews[i].get("content")
    ]

    if not candidate_reviews:
        return "No specific user quotes available for this theme."

    # If only 1 review, use it directly (shortened if needed)
    if len(candidate_reviews) == 1:
        return _sanitize_quote(candidate_reviews[0], candidate_reviews)

    # If llm_client is None and API key is not present for active provider, select candidate directly without LLM
    if llm_client is None and not _has_valid_api_key(cfg):
        # Deterministic quote selection fallback for offline testing
        selected = max(candidate_reviews, key=lambda c: len(c) if len(c.split()) <= 35 else 0)
        return _sanitize_quote(selected, candidate_reviews)

    prompt = f"""From the following reviews for the theme "{theme.get('name')}", pick the single 
most representative verbatim quote (max 40 words).

Rules:
- Copy the user's exact words — do NOT paraphrase
- Remove any personal names or contact info if present
- Return ONLY the quote text, nothing else

REVIEWS:
""" + "\n".join(f"- {c}" for c in candidate_reviews[:15])

    try:
        raw_quote = _call_llm(prompt, cfg, llm_client=llm_client)
        return _sanitize_quote(raw_quote, candidate_reviews)
    except Exception as exc:
        logger.warning("Quote selection LLM call failed (%s). Using fallback verbatim review.", exc)
        return _sanitize_quote(candidate_reviews[0], candidate_reviews)


def generate_action_ideas(
    top_themes: list[dict],
    quotes: list[str],
    cfg: dict,
    llm_client: Any = None,
) -> list[str]:
    """
    Generate exactly len(top_themes) concrete next steps grounded in the themes (EC-21).
    Each action idea must start with a capital verb and be <= 25 words.
    """
    target_count = len(top_themes)
    if target_count == 0:
        return []

    themes_summary = "\n".join(
        f"{i+1}. {t.get('name')}: {t.get('description')} (Quote: \"{q}\")"
        for i, (t, q) in enumerate(zip(top_themes, quotes))
    )

    if llm_client is None and not _has_valid_api_key(cfg):
        # Deterministic action idea generator for offline/fallback mode
        fallback_actions = []
        verbs = ["Fix", "Improve", "Streamline", "Optimize", "Enhance"]
        for i, t in enumerate(top_themes):
            verb = verbs[i % len(verbs)]
            action = f"{verb} {t.get('name').lower()} workflow to directly resolve core user issues reported in reviews."
            fallback_actions.append(action)
        return fallback_actions

    prompt = f"""You are a product manager at Groww. Based on these {target_count} user themes and quotes,
write exactly {target_count} concrete, specific action ideas (one per theme).

Each action idea must:
- Start with a capital verb (Fix, Add, Improve, Streamline, Redesign, etc.)
- Be grounded in the specific theme, not generic advice
- Be 1 sentence, max 25 words

Return ONLY a valid JSON array of {target_count} strings. No markdown fences, no explanation.

THEMES:
{themes_summary}
"""

    raw_response = _call_llm(prompt, cfg, llm_client=llm_client)
    json_text = _clean_json_response(raw_response)

    try:
        actions = json.loads(json_text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", json_text, flags=re.DOTALL)
        if match:
            actions = json.loads(match.group(0))
        else:
            # Fallback parse line-by-line
            actions = [
                re.sub(r"^\d+[\.\)]\s*", "", line).strip()
                for line in raw_response.splitlines()
                if line.strip() and not line.startswith("[") and not line.startswith("]")
            ]

    if not isinstance(actions, list):
        actions = [str(actions)]

    cleaned_actions: list[str] = []
    for i, item in enumerate(actions[:target_count]):
        act = str(item).strip().strip('"').strip("'")
        # Ensure it starts with a capital verb (EC-21)
        words = act.split()
        if words:
            first_word = words[0].strip(".,!?:;").lower()
            if first_word not in COMMON_VERBS:
                # Prepend appropriate default verb if missing
                default_verb = ["Fix", "Improve", "Streamline"][i % 3]
                act = f"{default_verb} {act[0].lower() + act[1:] if len(act) > 1 else act}"
            else:
                words[0] = words[0].capitalize()
                act = " ".join(words)

        # Enforce max 25 words
        words = act.split()
        if len(words) > 25:
            act = " ".join(words[:25]) + "."
        cleaned_actions.append(act)

    # Pad if LLM returned fewer than target_count (EC-23)
    while len(cleaned_actions) < target_count:
        idx = len(cleaned_actions)
        theme_name = top_themes[idx].get("name", "feature")
        cleaned_actions.append(f"Improve {theme_name.lower()} stability and user experience based on recent feedback.")

    return cleaned_actions


def format_pulse_prose(
    week_ending: str,
    review_count: int,
    weeks_back: int,
    top_themes: list[dict],
    quotes: list[str],
    actions: list[str],
) -> str:
    """Format pulse into the standardized human-readable weekly note."""
    lines = [
        f"Groww App — Weekly Review Pulse  [week ending {week_ending}]",
        f"Reviews analysed: {review_count}  |  Period: last {weeks_back} weeks",
        "",
        "TOP THEMES",
    ]

    for i, (t, q) in enumerate(zip(top_themes, quotes), start=1):
        lines.append(f"{i}. {t.get('name')} — {t.get('description')}")
        lines.append(f'   "{q}"')
        lines.append("")

    lines.append("ACTION IDEAS")
    for i, a in enumerate(actions, start=1):
        lines.append(f"{i}. {a}")

    return "\n".join(lines).strip()


def condense_prose(
    prose: str,
    max_words: int = 250,
) -> str:
    """
    Enforce <= max_words constraint deterministically (EC-18).
    Trims excessive description length while keeping all themes, quotes, and action ideas intact.
    """
    words = prose.split()
    if len(words) <= max_words:
        return prose

    # If exceeding, truncate theme descriptions down to 10 words
    logger.warning("EC-18: Pulse prose is %d words (> %d). Condensing...", len(words), max_words)
    lines = prose.splitlines()
    condensed_lines = []
    for line in lines:
        if re.match(r"^\d+\.\s+.*—", line):
            # Theme line
            prefix, desc = line.split("—", 1)
            desc_words = desc.strip().split()
            if len(desc_words) > 12:
                desc = " ".join(desc_words[:12]) + "…"
            condensed_lines.append(f"{prefix}— {desc}")
        else:
            condensed_lines.append(line)

    condensed = "\n".join(condensed_lines)
    if len(condensed.split()) > max_words:
        # Hard truncate non-header words to guarantee strict <= 250 words
        truncated_words = condensed.split()[:max_words]
        condensed = " ".join(truncated_words)

    return condensed


def generate_pulse(
    themes: list[dict],
    reviews: list[dict],
    config_path: str = "config/config.yaml",
    config: dict | None = None,
    week_ending: str | None = None,
    llm_client: Any = None,
) -> tuple[dict, str]:
    """
    Full Phase 3 pulse generation pipeline:
      1. Rank & select top 3 themes.
      2. Extract 1 representative verbatim quote per theme.
      3. Generate 3 grounded action ideas.
      4. Format prose and enforce <= 250 words limit.
      5. Construct pulse JSON payload and save snapshot to data/.

    Args:
        themes: List of theme dicts from cluster.py.
        reviews: List of sanitized review dicts.
        config_path: Path to config.yaml.
        config: Optional loaded configuration dictionary.
        week_ending: ISO date string YYYY-MM-DD.
        llm_client: Optional mock or real LLM client for testing.

    Returns:
        (pulse_payload, pulse_prose)
    """
    if not themes:
        raise PulseError("Cannot generate pulse with empty themes list.")

    cfg = config if config is not None else _load_config(config_path)
    pulse_cfg = cfg.get("pulse", {})
    review_cfg = cfg.get("review", {})
    output_cfg = cfg.get("output", {})

    top_n = int(pulse_cfg.get("top_themes", 3))
    max_words = int(pulse_cfg.get("max_words", 250))
    weeks_back = int(review_cfg.get("weeks_back", 10))
    data_dir = Path(output_cfg.get("data_dir", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    run_date = week_ending or datetime.now().strftime("%Y-%m-%d")

    # Select top themes (EC-12: if fewer than top_n themes, use available)
    top_themes = themes[:top_n]
    logger.info("Generating pulse for top %d themes...", len(top_themes))

    # 1. Quote selection (with pacing for Groq rate limits)
    quotes = []
    is_groq = cfg.get("llm", {}).get("provider", "").lower() == "groq"
    for i, t in enumerate(top_themes):
        if is_groq and i > 0:
            time.sleep(2.5)
        q = select_quote_for_theme(t, reviews, cfg, llm_client=llm_client)
        quotes.append(q)

    # 2. Action ideas generation
    if is_groq:
        time.sleep(2.5)
    actions = generate_action_ideas(top_themes, quotes, cfg, llm_client=llm_client)

    # 3. Format pulse prose
    prose = format_pulse_prose(
        week_ending=run_date,
        review_count=len(reviews),
        weeks_back=weeks_back,
        top_themes=top_themes,
        quotes=quotes,
        actions=actions,
    )

    # 4. Enforce <= 250 words (EC-18)
    if len(prose.split()) > max_words:
        prose = condense_prose(prose, max_words=max_words)

    word_count = len(prose.split())
    assert word_count <= max_words, f"EC-18 violation: Prose is {word_count} words (max {max_words})"

    # 5. Assemble structured pulse payload
    pulse_payload = {
        "week_ending": run_date,
        "review_count": len(reviews),
        "top_themes": [
            {
                "rank": i + 1,
                "name": t.get("name"),
                "description": t.get("description"),
                "review_count": len(t.get("review_indices", [])),
                "quote": q,
            }
            for i, (t, q) in enumerate(zip(top_themes, quotes))
        ],
        "action_ideas": actions,
        "word_count": word_count,
    }

    # 6. Save pulse snapshot to data/
    snapshot_path = data_dir / f"pulse_{run_date}.json"
    with snapshot_path.open("w", encoding="utf-8") as f:
        json.dump(pulse_payload, f, ensure_ascii=False, indent=2)

    logger.info("Pulse snapshot saved → %s (word count: %d)", snapshot_path, word_count)
    return pulse_payload, prose
